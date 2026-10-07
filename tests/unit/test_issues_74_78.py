"""Synthetic regressions for issues #78 (rank-1 power damage) and #74 (Xtraction beacon glow) - no game data.

#78: XML1 resolves a trigger attribute the trigger does not set against its same-named <event> at run
time (ps_rogue sstrike1's swings fire the event's Damage="L3"); the rank rungs override it only from
rank 2. StyleCollapse must backfill those leading ranks from the event, not zero them.
#74: XML2 retail ships same-named puzzles/beacon_xtraction*.IGB whose glow material was stripped; the
zones module force-imports XML1's four beacons and the V37 validator rule re-checks the shipment.
"""
import collections
import tempfile
import types
import xml.etree.ElementTree as ET
from pathlib import Path

from xml1build import common as C
from xml1build import heroes as H
from xml1build import zones as Z
from xml1build.validate import Check, Validator

# invented value codes: N2 = the invented event's rank-1 damage, N3/N4 = rung overrides
VALUES = '''<values>
<value name="N2" min="15" max="18"/><value name="N3" min="25" max="31"/><value name="N4" min="50" max="63"/>
<value name="S1" min="40"/><value name="S2" min="120"/><value name="S3" min="190"/>
<value name="E1" min="10"/><value name="E2" min="15"/>
</values>'''

# the issue #78 shape: root rung's triggers inherit damage/knockback from the event; rungs 2+ override
STYLE = '''<PowerStyle>
<FightMove name="whirl1" animenum="ea_power1" icon="0" powerup_tag="invtester_power">
<require cat="skill" item="invtester_smash" level="1"/>
<event name="whirl" inherit="punch" powerattack="true" damage="N2" knockback="S1">
<damageMod name="dmgmod_auto_knockback"/>
</event>
<trigger time="0" tag="1" name="powerusage" powerusage="E1"/>
<trigger time="0.4" tag="3" name="whirl" height="20" angle="30"/>
<trigger time="0.43" tag="4" name="whirl" height="0" angle="0"/>
</FightMove>
<FightMove name="whirl2" inherit="whirl1" fallback="whirl1">
<require cat="skill" item="invtester_smash" level="2"/>
<trigger tag="3" damage="N3" knockback="S2" maxrange="12"/>
<trigger tag="4" damage="N3" knockback="S2" maxrange="12"/>
</FightMove>
<FightMove name="whirl3" inherit="whirl2" fallback="whirl2">
<require cat="skill" item="invtester_smash" level="3"/>
<trigger tag="3" damage="N4" knockback="S3" maxrange="20"/>
<trigger tag="4" damage="N4" knockback="S3" maxrange="20"/>
</FightMove>
</PowerStyle>'''


def _collapse(style_text):
    values = H.Values(ET.fromstring(VALUES))
    talents = {'invtester_smash': {'power': '0', 'levels': 3}}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'ps_invtester.xml'
        p.write_bytes(style_text.encode('latin-1'))
        root = C.parse_x1_text(p)
    sc = H.StyleCollapse('invtester', root, values, talents, set())
    return sc, sc.run()


def _tv(sc, needle):
    for tvs in sc.talentvalues.values():
        for name, table in tvs.items():
            if needle in name:
                return name, [table.get(r) for r in sorted(table)]
    raise AssertionError(f'no talentvalue named *{needle}*')


def test_rank_one_inherits_the_events_damage_and_knockback():
    sc, out = _collapse(STYLE)
    assert _tv(sc, '_dmg_t3')[1] == ['15 18', '25 31', '50 63']      # rank 1 = the event's N2, not '0'
    assert _tv(sc, '_dmg_t4')[1] == ['15 18', '25 31', '50 63']
    assert _tv(sc, '_kb_t3')[1] == ['40', '120', '190']               # rank 1 = the event's S1
    fm = next(m for m in out.iter('FightMove') if (m.get('name') or '') == 'power1')
    ev = next(e for e in fm.iter('event'))
    assert ev.get('damage') == '15 18' and ev.get('knockback') == '40'
    trig = next(t for t in fm.iter('trigger') if t.get('tag') == '3')
    assert trig.get('damage').endswith('_dmg_t3') and trig.get('knockback').endswith('_kb_t3')


def test_rank_one_stays_zero_when_the_event_lacks_the_attribute():
    sc, _ = _collapse(STYLE)
    # maxrange (SHORT: rng) appears only from rank 2 (added by the rungs) and the event carries
    # none: the leading-rank fill stays '0' (no event value to inherit)
    name, table = _tv(sc, '_rng_t3')
    assert table == ['0', '12', '20'], (name, table)


# -------------------------------------------------------------------------------------------------- #74
def _zones_stub(imported, present):
    def _imp(rel, force=False):
        imported[rel] = force
        return types.SimpleNamespace(ok=True, status='written')

    ctx = types.SimpleNamespace(import_x1_asset=_imp, x1_path=lambda rel: None, x1_zones=lambda: [])
    z = types.SimpleNamespace(ctx=ctx, counts=collections.Counter(),
                              problems=collections.defaultdict(lambda: collections.defaultdict(set)))
    z.problem = lambda kind, item, where: z.problems[kind][item].add(where)
    z.x1_nonempty = lambda rel: present.get(rel, True)
    return z


def test_all_four_beacons_are_force_imported():
    imported = {}
    z = _zones_stub(imported, {})
    Z.Zones.force_xtraction_beacons(z)
    assert sorted(imported) == sorted(m + '.igb' for m in Z.XTRACTION_BEACON_MODELS)
    assert all(imported.values())                                     # force=True on every one
    assert not z.problems
    assert z.counts['xtraction_beacon_written'] == 4


def test_missing_beacon_source_is_a_problem_not_a_crash():
    imported = {}
    missing = {Z.XTRACTION_BEACON_MODELS[0] + '.igb': False}
    z = _zones_stub(imported, missing)
    Z.Zones.force_xtraction_beacons(z)
    assert Z.XTRACTION_BEACON_MODELS[0] + '.igb' not in imported
    assert 'xtraction_beacon_missing' in z.problems


# ---------------------------------------------------------------------------------------------- V37
def _validator(folder, files, x1_files=None, zones=()):
    v = Validator.__new__(Validator)
    v.reg = {n: dict(rel=n, owner=owner, source='invented') for n, (owner, _) in files.items()}
    for n, (_, data) in files.items():
        (folder / Path(n).name).write_bytes(data)
    v.idx = types.SimpleNamespace(get=lambda n: n if n in files else None,
                                  path=lambda n: folder / Path(n).name if n in files else None)
    v.ctx = types.SimpleNamespace(x1_path=lambda rel: (x1_files or {}).get(rel), x1_zones=lambda: list(zones))
    return v


def _xmlb(root):
    return C.encode_xmlb(root)


def _talents(rank1, rank2):
    """two talentvalues (invented trigger-scoped damage + knockback), levels 1..2."""
    tal = ET.Element('talents')
    t = ET.SubElement(tal, 'talent', {'name': 'invtester_smash'})
    tvs = ET.SubElement(t, 'talentvalues')
    for lvl, (dmg, kb) in enumerate((rank1, rank2), start=1):
        ET.SubElement(tvs, 'talentvalue', {'level': str(lvl), 'name': 'xin_smash_dmg_t3', 'value': dmg})
        ET.SubElement(tvs, 'talentvalue', {'level': str(lvl), 'name': 'xin_smash_kb_t3', 'value': kb})
    return tal


def _style(dmg_ref='%xin_smash_dmg_t3'):
    ps = ET.Element('PowerStyle')
    fm = ET.SubElement(ps, 'FightMove', {'name': 'power1'})
    ET.SubElement(fm, 'require', {'cat': 'skill', 'item': 'invtester_smash', 'level': '1'})
    ET.SubElement(fm, 'event', {'name': 'whirl', 'damage': '15 18', 'knockback': '40'})
    ET.SubElement(fm, 'trigger', {'name': 'whirl', 'tag': '3', 'damage': dmg_ref, 'knockback': '%xin_smash_kb_t3'})
    return ps


def test_v37_flags_zeroed_rank_one_damage():
    with tempfile.TemporaryDirectory() as td:
        files = {'data/talents/invtester.xmlb': ('heroes', _xmlb(_talents(('0', '0'), ('25 31', '120')))),
                 'data/powerstyles/x1_ps_invtester.xmlb': ('heroes', _xmlb(_style()))}
        v = _validator(Path(td), files)
        ck = Check('V37', 'test')
        v._v37_rank_one_damage(ck)
    assert len(ck.errors) == 2, ck.errors                   # damage and knockback
    assert any('_dmg' in e for e in ck.errors) and any('_kb' in e for e in ck.errors)


def test_v37_passes_when_rank_one_matches_the_event():
    with tempfile.TemporaryDirectory() as td:
        files = {'data/talents/invtester.xmlb': ('heroes', _xmlb(_talents(('15 18', '40'), ('25 31', '120')))),
                 'data/powerstyles/x1_ps_invtester.xmlb': ('heroes', _xmlb(_style()))}
        v = _validator(Path(td), files)
        ck = Check('V37', 'test')
        v._v37_rank_one_damage(ck)
    assert not ck.errors, ck.errors


def test_v37_passes_when_rank_one_zero_is_genuine():
    """the trigger names no same-named event -> XML1's own zero stands (phoenix telekinesis shape)."""
    ps = ET.Element('PowerStyle')
    fm = ET.SubElement(ps, 'FightMove', {'name': 'power1'})
    ET.SubElement(fm, 'trigger', {'name': 'invented_lift', 'tag': '3', 'damage': '%xin_smash_dmg_t3'})
    with tempfile.TemporaryDirectory() as td:
        files = {'data/talents/invtester.xmlb': ('heroes', _xmlb(_talents(('0', '0'), ('25 31', '120')))),
                 'data/powerstyles/x1_ps_invtester.xmlb': ('heroes', _xmlb(ps))}
        v = _validator(Path(td), files)
        ck = Check('V37', 'test')
        v._v37_rank_one_damage(ck)
    assert not ck.errors, ck.errors


def _beacon_fixture(folder, built=b'xml1 beacon bytes ', zone_text=None):
    files = {}
    x1 = {}
    for m in Z.XTRACTION_BEACON_MODELS:
        name = Path(m).name + '.igb'
        src = folder / ('x1_' + name)
        src.write_bytes(built)
        x1[m + '.igb'] = src
        built_path = folder / name
        built_path.write_bytes(built)
        files[m + '.igb'] = ('zones', built)
    zones = ()
    if zone_text is not None:
        zone = folder / 'inv_zone.eng'
        zone.write_bytes(zone_text)
        x1['maps/inv_zone.eng'] = zone
        zones = ('inv_zone',)
    return files, x1, zones


def test_v37_beacons_identical_and_covering():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        files, x1, zones = _beacon_fixture(folder, zone_text=b'<entity name="inv_point" model="puzzles/beacon_xtraction" />')
        v = _validator(folder, files, x1, zones=zones)
        ck = Check('V37', 'test')
        v._v37_xtraction_beacons(ck)
        assert not ck.errors, ck.errors
        assert ck.counts['xtraction_beacons_identical'] == 4
        # now corrupt one built beacon: the build kept a glow-less file
        (folder / 'beacon_xtraction.igb').write_bytes(b'stripped')
        ck2 = Check('V37', 'test')
        v._v37_xtraction_beacons(ck2)
        assert len(ck2.errors) == 1 and 'differs from the XML1 source' in ck2.errors[0]


def test_v37_beacon_outside_the_shipped_set_is_an_error():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        zone_text = b'<entity name="inv_point" model="puzzles/beacon_xtraction_future" />'
        files, x1, zones = _beacon_fixture(folder, zone_text=zone_text)
        v = _validator(folder, files, x1, zones=zones)
        ck = Check('V37', 'test')
        v._v37_xtraction_beacons(ck)
        assert len(ck.errors) == 1 and 'beacon_xtraction_future' in ck.errors[0], ck.errors
