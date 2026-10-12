"""Issue #36: the thrown grenade (xml1build.weapons grenade helpers) - made-up weapons, no game data."""
import xml.etree.ElementTree as ET

from xml1build import weapons as W

# invented weapons / grenades / spawners (the real ones: weapons.eng grenade=, the nuclear-plant spawners)
ZAPPER = {'name': 'wp_zapper', 'type': 'bullet', 'damage': 'L1', 'grenade': 'sparkbang'}
LOBBER = {'name': 'wp_lobber', 'type': 'projectile', 'damage': 'L3', 'grenade': 'smokebomb'}
PLAIN = {'name': 'wp_plain', 'type': 'bullet', 'damage': 'L1', 'grenade': W.DEFAULT_GRENADE}
NOGRENADE = {'name': 'wp_quiet', 'type': 'bullet', 'damage': 'L1'}


def powerstyle():
    root = ET.Element('PowerStyle')
    m = ET.SubElement(root, 'FightMove', {'name': 'power_attack', 'animenum': 'ea_power1'})
    ET.SubElement(m, 'trigger', {'name': 'weapon_fire', 'time': '0'})
    return root


def test_variant_grenade_name_and_suffix_parse():
    assert W.variant_grenade_name('x1_ps_toys_zapper', 'sparkbang') == 'x1_ps_toys_zapper_sparkbang'
    assert W.variant_grenade_name('x1_ps_toys_zapper', 'Sparkbang') == 'x1_ps_toys_zapper_sparkbang'
    assert W.variant_grenade('x1_ps_toys_zapper_sparkbang', {'sparkbang', 'smokebomb'}) == 'sparkbang'
    assert W.variant_grenade('x1_ps_toys_zapper', {'sparkbang', 'smokebomb'}) == ''
    # a weapon name that merely ends in a grenade word is not a grenade variant
    assert W.variant_grenade('x1_ps_toys_smokebomb_gun', {'smokebomb'}) == ''


def test_grenade_move_is_an_ai_selected_throw():
    m = W.grenade_move('sparkbang')
    a = {k.lower(): v for k, v in m.attrib.items()}
    # XML1's own aitype, kept: XMen2.exe's aitype table knows "grenade" (0x2dba6c); at the guns' priority the AI
    # never picks it, so the throw outranks the guns
    assert a['name'] == W.GRENADE_MOVE and a['aitype'] == 'grenade' and a['aireusetime'] == '7'
    assert int(a['priority']) > int(W.AI_PRIORITY)
    trig = {c.get('name'): {k.lower(): v for k, v in c.attrib.items()} for c in m if c.tag == 'trigger'}
    assert trig['grenade_projectile']['entity'] == 'sparkbang'
    assert trig['grenade_projectile']['filename'] == 'grenade_ents'
    assert trig['grenade_projectile']['actorbolt'] == 'Bip01 L Hand'
    assert trig['removebolton']['removebolton'] == 'true'


def test_apply_appends_the_throw_with_the_weapon_granade():
    root = powerstyle()
    rep = W.apply(root, PLAIN)
    assert rep['grenade_move_added'] == 1 and rep['grenade_grenade'] == 1
    moves = [m.get('name') for m in root.findall('FightMove')]
    assert moves == ['power_attack', W.GRENADE_MOVE]          # the shot stays, the throw is added
    # an explicit effective grenade (a spawner override) beats the weapon's own grenade=
    root2 = powerstyle()
    W.apply(root2, PLAIN, grenade='sparkbang')
    throw = root2.findall('FightMove')[1]
    ent = [c.get('entity') for c in throw.iter('trigger') if c.get('name') == W.GRENADE_TRIGGER]
    assert ent == ['sparkbang']
    # no grenade= on the weapon and none given: no throw
    root3 = powerstyle()
    rep3 = W.apply(root3, NOGRENADE)
    assert rep3['grenade_move_added'] == 0 and len(root3.findall('FightMove')) == 1
    # idempotent: a style that already throws keeps its single move
    W.apply(root2, PLAIN, grenade='sparkbang')
    assert len(root2.findall('FightMove')) == 2


def test_effective_grenade_spawner_override_beats_weapon():
    assert W.effective_grenade(ZAPPER, 'smokebomb') == 'smokebomb'     # the spawner names it: wins
    assert W.effective_grenade(ZAPPER, '') == 'sparkbang'              # the weapon's grenade=
    assert W.effective_grenade(NOGRENADE, 'sparkbang') == 'sparkbang'  # override alone
    assert W.effective_grenade(NOGRENADE, '') == ''                    # neither: no throw in XML1


def test_grenade_powerstyle_want_only_when_not_the_default():
    m = lambda s: 'x1_' + s                          # the build's map_powerstyle, invented names here
    assert W.grenade_powerstyle_want('ps_toys', 'wp_zapper', ZAPPER, '', m) == 'x1_ps_toys_zapper_sparkbang'
    assert W.grenade_powerstyle_want('ps_toys', 'wp_zapper', PLAIN, '', m) == ''   # default: the SPEC 29 name
    assert W.grenade_powerstyle_want('ps_toys', 'wp_quiet', NOGRENADE, '', m) == ''
    # the spawner override alone names the throw, even when the weapon has no grenade=
    assert W.grenade_powerstyle_want('ps_toys', 'wp_quiet', NOGRENADE, 'sparkbang', m) == 'x1_ps_toys_quiet_sparkbang'
    assert W.grenade_powerstyle_want('', 'wp_zapper', ZAPPER, '', m) == ''         # no style to carry the move


def test_grenade_override_votes_tally_by_character_and_file():
    def maps():
        a = ET.Element('root')
        ET.SubElement(a, 'entity', {'name': 'sp_a', 'classname': 'monsterspawnerent',
                                    'character': 'PretendSoldier', 'monster_grenade': 'sparkbang'})
        b = ET.Element('root')
        ET.SubElement(b, 'entity', {'name': 'sp_b', 'classname': 'monsterspawnerent',
                                    'character': 'PretendSoldier', 'monster_grenade': 'sparkbang'})
        ET.SubElement(b, 'entity', {'name': 'sp_c', 'classname': 'monsterspawnerent',
                                    'character': 'OtherSoldier', 'monster_grenade': 'smokebomb'})
        return a, b

    votes = W.grenade_override_votes([('maps/toy1.eng', maps()[0]), ('maps/toy2.eng', maps()[1])])
    assert votes == {'pretendsoldier': {'sparkbang': {'maps/toy1.eng', 'maps/toy2.eng'}},
                     'othersoldier': {'smokebomb': {'maps/toy2.eng'}}}
    unanimous = {ch: next(iter(gs)) for ch, gs in votes.items() if len(gs) == 1}
    assert unanimous == {'pretendsoldier': 'sparkbang', 'othersoldier': 'smokebomb'}

    c = ET.Element('root')
    ET.SubElement(c, 'entity', {'name': 'sp_d', 'classname': 'monsterspawnerent',
                                'character': 'OtherSoldier', 'monster_grenade': 'sparkbang'})
    split = W.grenade_override_votes([('maps/toy2.eng', maps()[1]), ('maps/toy3.eng', c)])
    assert sorted(split['othersoldier']) == ['smokebomb', 'sparkbang']   # disagreement: not unanimous
    assert len(split['othersoldier']['smokebomb']) == len(split['othersoldier']['sparkbang']) == 1


def test_moveset_variant_preserves_the_throw_and_other_triggers():
    root = ET.fromstring('<FightingStyle name="moveset_toy"><FightMove name="toy_throw">'
                         '<trigger name="grenade_projectile" entity="grenade" filename="toy_entities"/>'
                         '<trigger name="sound" sound="toy/throw"/></FightMove></FightingStyle>')
    W.apply_grenade(root, 'sparkbang')
    assert root[0][0].get('entity') == 'sparkbang'
    assert root[0][0].get('filename') == 'toy_entities'
    assert root[0][1].get('sound') == 'toy/throw'
    before = ET.tostring(root)
    W.apply_grenade(root, 'sparkbang')
    assert ET.tostring(root) == before


def test_moveset_selection_keeps_default_and_grants_only_the_override():
    m = lambda s: s
    assert W.grenade_moveset_want('moveset_toy', ZAPPER, '', m) == 'x1_moveset_toy_sparkbang'
    assert W.grenade_moveset_want('x1_moveset_toy', ZAPPER, '', m) == 'x1_moveset_toy_sparkbang'
    assert W.grenade_moveset_want('moveset_toy', PLAIN, '', m) == ''
    assert W.grenade_moveset_want('', ZAPPER, '', m) == ''
    assert W.grenade_moveset_want('', PLAIN, 'sparkbang', m) == 'x1_moveset_grenade_sparkbang'


def test_stats_grants_overridden_moveset_and_packages_both_style_variants():
    from test_gun_fightstyles import _builder, _stats
    from xml1build import characters as CH
    b = _builder([PLAIN])
    b.grenade_overrides = {'testtrooper': 'sparkbang'}
    b.grenade_style = lambda base, g: W.grenade_variant_name(base, g)
    stats = b.convert_stats(_stats('wp_plain'), 'xml1')
    assert stats.get('moveset1') == 'x1_moveset_grenade_sparkbang'
    b.variant_base = {stats.get('powerstyle'): 'ps_testgun'}
    b.grenade_variant_base = {stats.get('moveset1'): 'moveset_grenade'}
    b._grenade_deps = lambda v: [('xml', 'data/entities/toy_entities'), ('effect', 'toy/blast')]
    pkg = ET.fromstring('<packagedef><fightstyle filename="data/powerstyles/ps_testgun"/>'
                        '<fightstyle filename="data/fightstyles/moveset_grenade"/></packagedef>')
    CH._Builder.swap_variant_style(b, pkg, stats)
    entries = [(e.tag, e.get('filename')) for e in pkg]
    assert ('fightstyle', 'data/powerstyles/' + stats.get('powerstyle')) in entries
    assert ('fightstyle', 'data/fightstyles/' + stats.get('moveset1')) in entries
    assert entries.count(('xml', 'data/entities/toy_entities')) == 1
    before = ET.tostring(pkg)
    CH._Builder.swap_variant_style(b, pkg, stats)
    assert ET.tostring(pkg) == before
    # Asset-only bundles must explicitly load both variants too.
    empty = ET.Element('packagedef')
    CH._Builder.swap_variant_style(b, empty, stats)
    assert len([e for e in empty if e.tag == 'xml' and 'styles/' in e.get('filename')]) == 2


def test_validator_rejects_wrong_moveset_entity_registration_and_flash_mods():
    import types
    from xml1build import validate as V
    ents = ET.fromstring('<entities><entity name="sparkbang"/><entity name="flashbang" explodedamagemods="toy_mask_a toy_mask_b"/></entities>')
    fs = ET.fromstring('<FightingStyle name="moveset_toy"><FightMove><trigger '
                       'name="grenade_projectile" entity="wrongtoy"/></FightMove></FightingStyle>')
    blast = ET.fromstring('<entities><entity name="flashbang" '
                          'explodedamagemods="toy_override"/></entities>')
    trees = {'data/fightstyles/x1_moveset_toy_sparkbang.xmlb': fs,
             'data/entities/grenade_ents.xmlb': blast}
    fake = types.SimpleNamespace(
        ctx=types.SimpleNamespace(x1_path=lambda _: True, read_x1_xml=lambda _: ents),
        idx=types.SimpleNamespace(under=lambda prefix: [r for r in trees if r.startswith(prefix)]),
        tree=trees.get)
    check = V.Check('test', 'grenade chain')
    V.Validator._grenade_variant_files(fake, check)
    assert len(check.errors) == 3
    fs.set('name', 'x1_moveset_toy_sparkbang')
    fs[0][0].set('entity', 'sparkbang')
    blast[0].set('explodedamagemods', 'toy_mask_a toy_mask_b')
    fixed = V.Check('test', 'grenade chain')
    V.Validator._grenade_variant_files(fake, fixed)
    assert not fixed.errors
