"""SPEC 31-33 (2026-10-01 audits W2, G3, G5) on made-up data - no game files:
30 XML1's shared combat event values on the XML1 styles that inherit them (combat_events.apply_x1_shared_values),
31 XML1's ce_renderfx tint form -> XML2's cloaked renderfx (x1schema.convert_renderfx),
32 the SKILL pickup as xml2-fix's addSkillPoints('_ACTIVATOR_',1) to the hero who takes it (zones.items_to_add)."""
import collections
import types
import xml.etree.ElementTree as ET

from xml1build import combat_events as CE, x1schema as XS, zones as Z
from xml1build.heroes import Values

X1_VALUES = Values(ET.fromstring(
    '<values><value name="L1" min="4" max="5"/><value name="L2" min="9" max="11"/>'
    '<value name="L3" min="15" max="18"/><value name="L4" min="25" max="31"/>'
    '<value name="K1" min="40"/><value name="K2" min="120"/></values>'))
# the shipped XML2 shared events the made-up styles inherit from (XML2's numbers)
XML2_SHARED = ET.fromstring(
    '<events><event name="punch" type="ce_atk_punch" damage="2 3" knockback="40" damagescale="normal"/>'
    '<event name="punch_heavy" inherit="punch" damage="3 5" knockback="120"/>'
    '<event name="kick" type="ce_atk_kick" damage="2 3" knockback="40" damagescale="normal"/>'
    '<event name="throw" type="ce_atk_throw" impactdamage="3 5" throwspeed="400"/>'
    '<event name="sound" type="ce_sound"/></events>')

STYLE = """<PowerStyle>
<event name="slam" inherit="punch_heavy" knockback="190"/>
<event name="own_hit" inherit="punch" damage="50 63"/>
<FightMove name="attacklight1" animenum="ea_attack_light1">
  <trigger time="0.5" name="punch" arc="75" knockback="190" maxrange="84"/>
  <trigger time="0.1" name="sound" sound="x"/>
</FightMove>
<FightMove name="attacklight2" animenum="ea_attack_light2">
  <trigger time="0.4" name="punch" damage="9 9"/>
  <trigger time="0.6" name="slam"/>
  <trigger time="0.7" name="own_hit"/>
  <trigger time="0.8" name="punch" type="ce_atk_punch"/>
</FightMove>
<FightMove name="combo1" animenum="ea_attack_light3">
  <trigger time="0.3" tag="1" name="kick" knockback="305"/>
</FightMove>
<FightMove name="combo2" inherit="combo1">
  <trigger tag="1" name="kick" knockback="400"/>
</FightMove>
<FightMove name="grabthrow" animenum="ea_grab_throw">
  <trigger time="0.4" name="throw"/>
</FightMove>
</PowerStyle>"""


def moves(root):
    return {m.get('name'): m for m in root if m.tag == 'FightMove'}


def effective(root, trigger, attr, shared=XML2_SHARED):
    """the value a trigger fires with: its own, else up its chain (style events, then the shared table) - the
    attribute copy XMen2.exe makes when an event inherits (0x501630, 0x4dce80)."""
    events = {e.get('name').lower(): e for e in root if e.tag == 'event'}
    table = {e.get('name').lower(): e for e in shared}
    el, seen = trigger, set()
    while el is not None and id(el) not in seen:
        seen.add(id(el))
        if el.get(attr) is not None:
            return el.get(attr)
        if el.get('type'):
            return None
        base = (el.get('inherit') or el.get('name') or '').lower()
        nxt = events.get(base)
        el = nxt if nxt is not None and nxt is not el else table.get(base)
    return None


# ---------------------------------------------------------------------------------------------- SPEC 33 (G3)
def test_shared_values_before_after_measured_on_one_style():
    root = ET.fromstring(STYLE)
    m = moves(root)
    light1 = m['attacklight1'][0]
    slam = m['attacklight2'][1]
    before = (effective(root, light1, 'damage'), effective(root, slam, 'damage'))
    assert before == ('2 3', '3 5')                       # XML2's shipped punch / punch_heavy
    c = CE.apply_x1_shared_values(root, X1_VALUES)
    after = (effective(root, light1, 'damage'), effective(root, slam, 'damage'))
    assert after == ('4 5', '9 11')                       # XML1's L1 / L2
    # knockback is XML1's own on the trigger, and K1 / K2 equal XML2's anyway: nothing written
    assert light1.get('knockback') == '190' and 'damagescale' not in light1.attrib
    assert c[f'{CE.X1_SHARED_KIND}:punch.damage'] == 1 and c[f'{CE.X1_SHARED_KIND}:punch_heavy.damage'] == 1


def test_shared_values_leave_overrides_types_and_tag_updates_alone():
    root = ET.fromstring(STYLE)
    CE.apply_x1_shared_values(root, X1_VALUES)
    m = moves(root)
    l2 = list(m['attacklight2'])
    assert l2[0].get('damage') == '9 9'                   # sets its own damage
    assert l2[1].get('damage') is None                    # names the style event slam, which carries the value
    assert root[0].get('damage') == '9 11' and root[1].get('damage') == '50 63'
    assert l2[3].get('damage') is None                    # a type: not an inheritor
    assert m['attacklight1'][1].get('damage') is None     # sound: not an event XML2 changed
    assert m['combo1'][0].get('damage') == '4 5'          # the parent kick
    assert m['combo2'][0].get('damage') is None           # tag update of the inherited kick: keeps the parent's
    throw = m['grabthrow'][0]
    assert [d.get('name') for d in throw] == ['dmgmod_auto_knockback'] and throw.get('damage') is None


def test_shared_values_idempotent_and_codes_without_values():
    root = ET.fromstring(STYLE)
    CE.apply_x1_shared_values(root, X1_VALUES)
    snap = ET.tostring(root)
    assert not CE.apply_x1_shared_values(root, X1_VALUES) and ET.tostring(root) == snap
    raw = ET.fromstring(STYLE)
    CE.apply_x1_shared_values(raw)                         # no values table: XML1's code itself
    assert moves(raw)['attacklight1'][0].get('damage') == 'L1'


def test_shared_values_style_event_of_the_shared_name_shadows_it():
    root = ET.fromstring('<PowerStyle><event name="punch" inherit="punch" damage="7 8"/>'
                         '<FightMove name="a"><trigger time="0" name="punch"/></FightMove></PowerStyle>')
    c = CE.apply_x1_shared_values(root, X1_VALUES)
    assert not c and root[1][0].get('damage') is None and root[0].get('damage') == '7 8'


def test_x1schema_runs_the_rebase_first_then_the_values_on_styles_only():
    root = ET.fromstring('<PowerStyle><FightMove name="a"><trigger time="0" name="punch"/></FightMove></PowerStyle>')
    XS.convert(root, 'data/powerstyles/ps_test.eng', None, X1_VALUES)
    assert root[0][0].get('damage') == '4 5'
    zone = ET.fromstring('<world><trigger time="0" name="punch"/></world>')
    XS.convert(zone, 'maps/test/zone.eng', None, X1_VALUES)
    assert zone[0].get('damage') is None


# ---------------------------------------------------------------------------------------------- SPEC 31 (G5)
RENDERFX = """<PowerStyle><FightMove name="power_boost">
  <trigger time="0.35" name="tintout" type="ce_renderfx" tint="true" solid="true" alpha="true" rgba="0 0 0 0.5"/>
  <trigger time="0.85" name="tintin" type="ce_renderfx" remove="true" tint="true" solid="true"/>
  <trigger time="0.9" name="other" type="ce_renderfx" add="burning"/>
  <trigger time="1" name="tint2" type="CE_RenderFX" Tint="true" RGBA="0.1 0 0.2 1" life="1.5"/>
</FightMove></PowerStyle>"""


def test_renderfx_tint_form_becomes_cloaked():
    root = ET.fromstring(RENDERFX)
    assert len(XS.renderfx_x1_elements(root)) == 3
    c = XS.convert_renderfx(root)
    out, back, other, tint2 = list(root[0])
    assert dict(out.attrib) == {'time': '0.35', 'name': 'tintout', 'type': 'ce_renderfx', 'add': 'cloaked'}
    assert dict(back.attrib) == {'time': '0.85', 'name': 'tintin', 'type': 'ce_renderfx', 'remove': 'cloaked'}
    assert dict(other.attrib) == {'time': '0.9', 'name': 'other', 'type': 'ce_renderfx', 'add': 'burning'}
    assert tint2.get('add') == 'cloaked' and tint2.get('life') == '1.5' and 'Tint' not in tint2.attrib
    assert c == collections.Counter({'renderfx:add': 2, 'renderfx:remove': 1})
    assert not XS.renderfx_x1_elements(root)
    snap = ET.tostring(root)
    assert not XS.convert_renderfx(root) and ET.tostring(root) == snap


def test_renderfx_runs_through_convert_on_styles():
    root = ET.fromstring(RENDERFX)
    c = XS.convert(root, 'data/powerstyles/ps_grsoelite.eng')
    assert c['renderfx:add'] == 2 and c['renderfx:remove'] == 1


# ---------------------------------------------------------------------------------------------- SPEC 32 (W2)
ITEMS = ET.fromstring('<items><item name="XP" type="xp" model="pickups/experience_point"/>'
                      '<item name="SKILL" displayname="Skill Points" type="skill" description="Free skill point!" '
                      'model="pickups/skill_point"/><item name="STAT" type="stat"/></items>')
ZONE = """<world><entity name="world" mission="haarp" level="6" soundfile="harext"/>
<entity name="item_skill" classname="inventoryent" inventoryitem="skill" count="1" actontouch="true"/>
<entinst type="item_skill"><inst name="item_skill" pos="2160 -3144 288"/></entinst></world>"""


def zones_stub(curve='xml1'):
    z = Z.Zones.__new__(Z.Zones)
    z.ctx = types.SimpleNamespace(read_x1_xml=lambda rel: ITEMS,
                                  opt=lambda k: {'xp_curve': curve, 'frontend': 'xml2'}.get(k))
    z.xp_pickups = {}
    z.item_refs = collections.defaultdict(set)
    z.counts = collections.Counter()
    z.problems = collections.defaultdict(lambda: collections.defaultdict(set))
    return z


def test_skill_pickup_calls_xml2fix_add_skill_points_for_the_picker():
    """SPEC 32: XML1's SKILL item keeps its name; its onactivate is xml2-fix's addSkillPoints('_ACTIVATOR_',1)."""
    z = zones_stub()
    root = ET.fromstring(ZONE)
    assert root[1].get('inventoryitem') == 'skill'                # the entity is left as XML1 wrote it
    z.item_refs['skill'].add('haarp/ext/haarp_ext03')
    added, report = z.items_to_add(list(ITEMS), set())
    item = next(i for i in added if i.get('name') == 'SKILL')
    assert item.get('onactivate') == "addSkillPoints('_ACTIVATOR_',1)" and item.get('activateonpickup') == 'true'
    assert item.get('type') == 'item' and item.get('model') == 'pickups/skill_point'
    assert item.get('displayname') == 'Skill Points' and item.get('description') == 'Free skill point!'
    assert not any('awardXPToPlayable' in (i.get('onactivate') or '') for i in added)
    assert not any('setXP' in (i.get('onactivate') or '') for i in added)
    assert Z.ITEM_TYPE_MAP['skill'][1]['onactivate'] == Z.SKILL_PICKUP_SCRIPT == "addSkillPoints('_ACTIVATOR_',1)"
    # the same on XMen2.exe's curve: the call does not depend on XP tables
    z2 = zones_stub('xml2')
    z2.item_refs['skill'].add('z')
    added2, _ = z2.items_to_add(list(ITEMS), set())
    assert next(i for i in added2 if i.get('name') == 'SKILL').get('onactivate') == "addSkillPoints('_ACTIVATOR_',1)"


def test_add_skill_points_is_in_the_script_api_of_every_build():
    """the lint knows the call in seat and menu builds alike (common.XML2FIX_ALWAYS_FUNCS, scripts_transform)."""
    from xml1build import common as C, scripts_transform as ST
    assert 'addSkillPoints' in C.XML2FIX_ALWAYS_FUNCS and ST.XML2FIX_API['addSkillPoints'] == ('n', 'ai')
    assert 'addSkillPoints' in ST.XML2FIX_DATA_FUNCS and 'seatParty' not in ST.XML2FIX_DATA_FUNCS


# ---------------------------------------------------------------------------------------------- SPEC 32.1
def inventory(affix_enhancements, items):
    top = ET.Element('inventory')
    pre = ET.SubElement(top, 'prefixes')
    for _ in range(affix_enhancements):
        ET.SubElement(pre, 'enhancement')
    for name, n in items:
        it = ET.SubElement(top, 'item', {'name': name})
        for _ in range(n):
            ET.SubElement(it, 'enhancement')
    return top


def test_enhancement_pool_cuts_the_overflowing_item_and_every_later_one():
    top = inventory(372, [('A', 2), ('B', 0), ('EQ', 2), ('C', 0)])
    assert Z.enhancement_pool_cut(top, 375) == [('EQ', 374), ('C', 376)]
    assert Z.enhancement_pool_cut(inventory(373, [('A', 2), ('B', 0)]), 375) == []


def test_enhancement_pool_follows_the_fix_the_port_asks_for():
    """SPEC 32.1 / 32.3: the build is checked against the pool the shipped ini asks xml2-fix for (512 since 1.3.0);
    XMen2.exe's own 375 stays the stock number."""
    from xml1build import fix_ini as FI
    assert FI.LIMITS['ItemEnhancements'] == '512' and 'ItemEnhancements' in FI.PORT_OWNED['Limits']
    assert Z.ITEM_ENHANCEMENT_POOL == 512 and Z.ITEM_ENHANCEMENT_POOL_STOCK == 375
    top = inventory(374, [('EQ', 1), ('C', 2)])
    assert Z.enhancement_pool_cut(top) == [] and Z.enhancement_pool_cut(top, 375) == [('C', 375)]
    assert Z.enhancement_pool_cut(inventory(500, [('A', 12), ('B', 1)])) == [('B', 512)]


def test_pickup_items_go_before_the_xml1_equipment():
    z = zones_stub()
    x1 = [ET.fromstring('<item name="RING" type="equipment"/>')] + list(ITEMS)
    z.item_refs['ring'].add('z')
    z.item_refs['skill'].add('z')
    z.item_refs['stat'].add('z')
    real = z.translate_item

    def translate(c):
        if c.get('name') == 'RING':                       # an equipment item that keeps its enhancements (SPEC 21)
            el = ET.Element('item', {'name': 'RING', 'type': 'equipment'})
            ET.SubElement(ET.SubElement(el, 'enhancement'), 'powerup')
            return el, None
        return real(c)
    z.translate_item = translate
    added, _ = z.items_to_add(x1, set())
    assert [i.get('name') for i in added] == ['SKILL', 'STAT', 'RING']   # file order, the enhancement-free first
    top = inventory(374, [(i.get('name'), Z.item_enhancements(i)) for i in added])
    assert Z.enhancement_pool_cut(top, 375) == []          # the pickups load; RING's one enhancement is the 375th

def test_stat_pickup_awards_a_spendable_point_only_to_its_collector():
    z = zones_stub('xml1')
    z.item_refs['stat'].add('synthetic_zone')
    added, _ = z.items_to_add(list(ITEMS), set())
    item = next(i for i in added if i.get('name') == 'STAT')
    assert item.get('type') == 'item' and item.get('activateonpickup') == 'true'
    assert item.get('onactivate') == "addStatPoints('_ACTIVATOR_',1)"
    assert 'permanentStatBoost' not in ET.tostring(item, encoding='unicode')
    from xml1build import common as C, scripts_transform as ST
    assert 'addStatPoints' in C.XML2FIX_ALWAYS_FUNCS
    assert ST.XML2FIX_API['addStatPoints'] == ('n', 'ai')
