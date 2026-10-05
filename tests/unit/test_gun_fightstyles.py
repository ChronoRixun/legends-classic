"""Issue #52: a gun's fighting style replaces the holder's own, and a style XML2 ships too thin goes under its own
name (x1names.X1_OWN_FIGHTSTYLES). Invented weapons, styles and stats entries built in code - no game data."""
import threading
import types
import xml.etree.ElementTree as ET
from unittest.mock import patch

from xml1build import characters as CH
from xml1build import common as C
from xml1build import weapons as W
from xml1build.lib import x1names as N

OWN = frozenset({'fightstyle_testlong'})          # an invented style XML2 "ships too thin"
RIFLE = {'name': 'wp_testrifle', 'type': 'bullet', 'fightstyle': 'fightstyle_testlong', 'powerstyle': 'ps_testgun',
         'model': 'models/test/rifle', 'actorbolt': 'Bip01 R Hand'}
SIDEARM = {'name': 'wp_testhip', 'type': 'projectile', 'fightstyle': 'fightstyle_testhip', 'powerstyle': 'ps_testgun',
           'model': 'models/test/hip'}
CLUB = {'name': 'wp_testclub', 'category': 'melee', 'fightstyle': 'fightstyle_testclub', 'powerstyle': 'ps_testmelee',
        'model': 'models/test/club'}
BARE = {'name': 'wp_testbare', 'type': 'bullet', 'model': 'models/test/bare'}      # a gun without a style


def test_gun_fightstyle_only_for_guns_that_name_one():
    assert W.gun_fightstyle(RIFLE) == 'fightstyle_testlong'
    assert W.gun_fightstyle(SIDEARM) == 'fightstyle_testhip'
    assert W.gun_fightstyle(dict(RIFLE, type='Flame')) == 'fightstyle_testlong'
    assert W.gun_fightstyle(CLUB) == ''                     # melee: the holder keeps his own style
    assert W.gun_fightstyle(BARE) == '' and W.gun_fightstyle(None) == '' and W.gun_fightstyle({}) == ''


def test_own_styles_map_style_anim_db_and_animations_attribute():
    # no collision table (no game data): no character anim DB collides with XML2's
    with patch.object(N, 'X1_OWN_FIGHTSTYLES', OWN), patch.object(N, '_collisions', lambda: {}):
        assert N.map_fightstyle('fightstyle_testlong') == 'x1_fightstyle_testlong'
        assert N.map_fightstyle('FightStyle_TestLong') == 'x1_fightstyle_testlong'
        assert N.map_animdb('fightstyle_testlong') == 'x1_fightstyle_testlong'
        assert not N.shares_xml2_animdb('fightstyle_testlong')
        # idempotent: an already-mapped name stays (packages map entries that were mapped before)
        assert N.map_fightstyle('x1_fightstyle_testlong') == 'x1_fightstyle_testlong'
        assert N.map_animdb('x1_fightstyle_testlong') == 'x1_fightstyle_testlong'
        # the style file's animations= follows its anim DB; other styles keep XML2's shared DB and file
        assert C.map_attr('Animations', 'fightstyle_testlong') == 'x1_fightstyle_testlong'
        assert C.map_attr('animations', 'fightstyle_testother') == 'fightstyle_testother'
        assert N.map_fightstyle('fightstyle_testother') == 'fightstyle_testother'
        assert N.map_animdb('fightstyle_testother') == 'fightstyle_testother'
        assert N.shares_xml2_animdb('fightstyle_testother') and N.shares_xml2_animdb('moveset_testother')
        sent = C.map_package_entry('fightstyle', 'data/fightstyles/fightstyle_testlong.eng')
        assert sent == ('fightstyle', 'data/fightstyles/x1_fightstyle_testlong')
        assert C.map_package_entry('actoranimdb', 'actors/fightstyle_testlong.igb')[1] == 'x1_fightstyle_testlong'


def test_fightstyle_names_include_own_styles():
    assert N.is_fightstyle_name('fightstyle_testa') and N.is_fightstyle_name('X1_FightStyle_TestA')
    assert not N.is_fightstyle_name('moveset_testa') and not N.is_fightstyle_name('x1_ps_testa')
    assert not N.is_fightstyle_name(None) and not N.is_fightstyle_name('')


def test_validator_rule_wants_the_gun_style_alone():
    m = lambda n: 'x1_' + n if n in OWN else n          # noqa: E731 - the build's map_fightstyle
    assert W.fightstyle_problems(['x1_fightstyle_testlong'], RIFLE, m) == []
    assert W.fightstyle_problems(['fightstyle_testhip'], SIDEARM, m) == []
    # the entry kept its own style: XMen2.exe would use one of them (the lowest talent id), not reliably the gun's
    assert W.fightstyle_problems(['fightstyle_testbrawl'], RIFLE, m)
    assert W.fightstyle_problems(['fightstyle_testbrawl', 'x1_fightstyle_testlong'], RIFLE, m)
    assert W.fightstyle_problems([], RIFLE, m)
    assert W.fightstyle_problems(['fightstyle_testlong'], RIFLE, m)       # XML2's thin file, not the own copy
    # melee weapons, style-less guns and unarmed entries are not this rule's business
    assert W.fightstyle_problems(['fightstyle_testbrawl'], CLUB, m) == []
    assert W.fightstyle_problems(['fightstyle_testbrawl'], BARE, m) == []
    assert W.fightstyle_problems(['fightstyle_testbrawl'], None, m) == []


def _builder(weapons):
    ctx = types.SimpleNamespace(count=lambda *a: None, warn=lambda *a: None, error=lambda *a: None,
                                defer=lambda *a: None, note=lambda *a: None, sound_bank_rel=lambda sd: None)
    b = CH._Builder.__new__(CH._Builder)
    b.ctx, b.lock = ctx, threading.RLock()
    b.detail = {'dropped_attrs': [], 'dropped_children': [], 'notes': [], 'talents_added': [],
                'immunity_refs': []}
    b.x1_weapons = {w['name']: w for w in weapons}
    b.x1_talents = {}
    b.talents = []
    b.style = lambda kind, name, rel=None: N.map_fightstyle(name) if kind == 'fightstyles' else name
    b.weapon_style = lambda style, weapon, wname: W.variant_name(style, wname)
    b.ensure_talent = lambda name, fs, who: b.talents.append((name, fs))
    b._model_ok = lambda *a: True
    b.exists = lambda rel: True
    b.immunity_name = lambda el: None
    return b


def _stats(weapon, *talents):
    st = ET.Element('stats', {'name': 'TestTrooper', 'powerstyle': 'ps_testgun', 'weapon': weapon})
    for t in talents:
        ET.SubElement(st, 'talent', {'name': t, 'level': '1'})
    return st


def _fight_talents(el):
    return [t.get('name') for t in el.iter('talent') if N.is_fightstyle_name(t.get('name'))]


def test_convert_stats_replaces_the_style_of_a_gun_holder():
    with patch.object(N, 'X1_OWN_FIGHTSTYLES', OWN):
        b = _builder([RIFLE, SIDEARM, CLUB])
        out = b.convert_stats(_stats('wp_testrifle', 'fightstyle_testbrawl', 'test_toughness'), 'xml1')
        assert _fight_talents(out) == ['x1_fightstyle_testlong']
        assert [t.get('name') for t in out.iter('talent')][0] == 'test_toughness'     # other talents kept
        assert ('x1_fightstyle_testlong', True) in b.talents                         # a fightstyle="true" talent
        assert any(d[1] == 'talent fightstyle_testbrawl' for d in b.detail['dropped_children'])
        assert out.get('powerstyle') == 'x1_ps_testgun_testrifle'                    # SPEC 29 variant unchanged
        # a gun with an XML2-shared style, and a gun holder without a style of his own
        out = b.convert_stats(_stats('wp_testhip', 'fightstyle_testbrawl'), 'xml1')
        assert _fight_talents(out) == ['fightstyle_testhip']
        out = b.convert_stats(_stats('wp_testrifle'), 'xml1')
        assert _fight_talents(out) == ['x1_fightstyle_testlong']


def test_convert_stats_leaves_melee_holders_alone():
    with patch.object(N, 'X1_OWN_FIGHTSTYLES', OWN):
        b = _builder([CLUB])
        out = b.convert_stats(_stats('wp_testclub', 'fightstyle_testbrawl'), 'xml1')
        assert _fight_talents(out) == ['fightstyle_testbrawl']
        out = b.convert_stats(_stats('wp_testclub'), 'xml1')                     # no style: the weapon's, as before
        assert _fight_talents(out) == ['fightstyle_testclub']
        out = b.convert_stats(_stats('', 'fightstyle_testbrawl'), 'xml1')       # unarmed (pistol bosses, brawlers)
        assert _fight_talents(out) == ['fightstyle_testbrawl']
