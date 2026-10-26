"""SPEC 105 (gap row C10) on made-up data - no game files: where every XML1 text string went
(tools/xml1build/text_trace.py, validator V66), the codex tab (frontend.attribute_tabs) and the repaired zoneinfo
slips (zones.x1_zoneinfo_entries)."""
import xml.etree.ElementTree as ET

from xml1build import frontend as F
from xml1build import text_trace as T
from xml1build import zones as Z


def tree(xml):
    return ET.fromstring(xml)


class _Values:
    """heroes.Values stand-in: ^L3 -> 15-18, anything else is its own word."""

    def resolve_text(self, text):
        return text.replace('^L3', '15-18').replace('^', '')


def make_port(files, **facts):
    return T.Port({rel: tree(x) for rel, x in files.items()}, dict({'x1_values': _Values()}, **facts))


def one(rel, xml, port):
    rows = T.trace([(rel, tree(xml))], port)
    return rows


def classes(rows):
    return [(r.cls, r.rule) for r in rows]


# ------------------------------------------------------------------------------------------------ the classes
def test_shipped_and_moved_and_unaccounted():
    port = make_port({'subtitles/a.engb': '<s><line text="same"/></s>',
                      'conversations/c.engb': '<c><line text="moved here"/></c>'})
    assert classes(one('subtitles/a.eng', '<s><line text="same"/></s>', port)) == [('shipped', '')]
    # a regrouped table: the same text under another key is 'moved'
    port = make_port({'conversations/c.engb': '<c><line text="x"/><line text="moved here"/></c>'})
    assert classes(one('conversations/c.eng', '<c><line text="moved here"/></c>', port)) == [('moved', '')]
    # a strict table (subtitles) must keep the text under its own key: a copy elsewhere is no proof
    port = make_port({'subtitles/a.engb': '<s><line text="other"/></s>', 'subtitles/b.engb': '<s><line text="x"/></s>'})
    assert classes(one('subtitles/a.eng', '<s><line text="x"/></s>', port)) == [('unaccounted', '')]
    assert classes(one('subtitles/gone.eng', '<s><line text="x"/></s>', port)) == [('unaccounted', '')]


def test_a_tab_the_reader_turned_into_a_space_is_the_same_string():
    port = make_port({'data/codex.engb': '<codex><character name="a" description="one&#9;two"/></codex>'})
    assert classes(one('data/codex.eng', '<codex><character name="a" description="one two"/></codex>', port)) == [
        ('shipped', '')]
    port = make_port({'data/codex.engb': '<codex><character name="magnetoscripted" description="x&#9;y"/></codex>'})
    assert classes(one('data/codex.eng', '<codex><character name="Magneto" description="x y"/></codex>', port)) == [
        ('shipped', '')]


def test_speaker_tokens_are_rewritten_only_for_the_named_renames():
    ok = [('%ALISON%Hi', '%MAGMA%Hi'), ('%FROST%Hi', '%EMMA%Hi'), ('%COLOSSUS%Hi %COLOSSUS%', '%COLOSSUS_X1DOUBLE%Hi %COLOSSUS_X1DOUBLE%'),
          ('%CYCLOPS%Hi', '%CYCLOPS_SCRIPTED%Hi'), ('%ALISON%Hi', '%ALISON_SCRIPTED%Hi')]
    for old, new in ok:
        assert T.speaker_rewrite(old, new), (old, new)
    bad = [('%ALISON%Hi', '%STORM%Hi'), ('%ALISON%Hi', '%MAGMA%Hello'), ('%A%x%B%', '%A%x'), ('%ALISON%Hi', '%MAGMA%Hi%X%')]
    for old, new in bad:
        assert not T.speaker_rewrite(old, new), (old, new)
    port = make_port({'conversations/c.engb': '<c><line text="%MAGMA%Hi"/></c>'})
    assert classes(one('conversations/c.eng', '<c><line text="%ALISON%Hi"/></c>', port)) == [('rewritten', 'speaker-token')]
    port = make_port({'conversations/c.engb': '<c><line text="%STORM%Hi"/></c>'})
    assert classes(one('conversations/c.eng', '<c><line text="%ALISON%Hi"/></c>', port)) == [('unaccounted', '')]


def test_menu_code_escape_and_extra_credit_trim_are_checked_by_running_the_rule():
    credit = '<credits><line text="NYC Acolyte #1"/></credits>'
    port = make_port({'data/credits.engb': '<credits><line text="NYC Acolyte |#1"/></credits>'})
    assert classes(one('data/credits.eng', credit, port)) == [('rewritten', 'menu-code-escape')]
    port = make_port({'data/credits.engb': '<credits><line text="NYC Acolyte #1"/></credits>'})
    assert classes(one('data/credits.eng', credit, port)) == [('shipped', '')]
    port = make_port({'data/credits.engb': '<credits><line text="something else"/></credits>'})
    assert classes(one('data/credits.eng', credit, port)) == [('unaccounted', '')]
    dr = '<dangerroom><COURSE name="C1" outro="Well Done!\\n\\nYou can also earn these extra credits: x"/></dangerroom>'
    port = make_port({'data/dangerroom.engb': '<dangerroom><COURSE name="C1" outro="Well Done!"/></dangerroom>'})
    assert classes(one('data/dangerroom.eng', dr, port)) == [('rewritten', 'extra-credit-trim')]
    port = make_port({'data/dangerroom.engb': '<dangerroom><COURSE name="C1" outro="Lost"/></dangerroom>'})
    assert classes(one('data/dangerroom.eng', dr, port)) == [('unaccounted', '')]


def test_value_codes_are_resolved_text_not_a_lost_string():
    x1 = '<characters><stats name="a"><Talent name="t"><level description="^L3 Damage"/></Talent></stats></characters>'
    port = make_port({'data/herostat.engb': '<characters><stats name="a"><talent name="t"><level description="15-18 Damage"/></talent></stats></characters>'})
    assert classes(one('data/herostat.eng', x1, port)) == [('rewritten', 'value-codes')]
    port = make_port({'data/herostat.engb': '<characters/>'})
    assert classes(one('data/herostat.eng', x1, port)) == [('unaccounted', '')]


def test_policies_are_structural():
    port = make_port({'data/items.engb': '<inventory><item name="HAVE" displayname="Theirs"/></inventory>'},
                     item_names=frozenset(('have',)), unused_missions=frozenset(('dead',)),
                     talent_names=frozenset(('known',)))
    items = '<inventory><item name="have" displayname="Mine"/><item name="other" displayname="Other"/></inventory>'
    assert classes(one('data/items.eng', items, port)) == [('xml2', 'item-table'), ('dropped', 'item-not-added')]
    strings = '<strings><string id="7" text="x"/></strings>'
    assert classes(one('data/strings.eng', strings, port)) == [('xml2', 'strings-by-id')]
    menu = '<MENU><item name="a" text="x"/></MENU>'
    assert classes(one('ui/menus/m.eng', menu, port)) == [('xml2', 'pc-menus')]
    mission = '<MISSION descname="D" description="E"><OBJECTIVE name="o" descname="O" description="P"/></MISSION>'
    assert classes(one('data/missions/dead.eng', mission, port)) == [
        ('dropped', 'mission-select'), ('dropped', 'mission-select'), ('dropped', 'unused-mission'), ('dropped', 'unused-mission')]
    live = one('data/missions/live.eng', mission, port)
    assert classes(live) == [('dropped', 'mission-select'), ('dropped', 'mission-select'),
                             ('unaccounted', ''), ('unaccounted', '')]
    talents = ('<Talents><Talent name="fightstyle_x" description="a"/><Talent name="known" description="b"/>'
               '<Talent name="never" description="c"/></Talents>')
    assert classes(one('data/shared_talents.eng', talents, port)) == [
        ('dropped', 'unused-shared-talent'), ('unaccounted', ''), ('dropped', 'unused-shared-talent')]
    cut = '<conversation><line text="gone"/></conversation>'
    assert classes(one('conversations/nyc/riots/3_2_6.eng', cut, port)) == [('dropped', 'cut-conversation')]


def test_maps_are_not_text_tables():
    assert T.trace([('maps/x/y.eng', tree('<w><e name="a" text="b"/></w>'))], make_port({})) == []


def test_every_policy_and_rule_has_a_reason():
    legend = T.reasons()
    for rule in T.REWRITES:
        assert legend[rule].strip()
    for pid, cls, why, _m in T.POLICIES:
        assert cls in T.CLASSES and why.strip() and legend[pid] == why


# ------------------------------------------------------------------------------------------------ whitespace in raw XML
def test_raw_tabs_are_found_and_must_survive():
    raw = b'<codex><character name="a" description="one\ttwo"/><character name="b" description="plain"/></codex>'
    assert T.raw_whitespace_values(raw) == ['one\ttwo']
    port = make_port({'data/codex.engb': '<codex><character name="a" description="one two"/></codex>'})
    assert T.lost_whitespace([('data/codex.eng', raw)], port) == [('data/codex.eng', 'one\ttwo')]
    port = make_port({'data/codex.engb': '<codex><character name="a" description="one&#9;two"/></codex>'})
    assert T.lost_whitespace([('data/codex.eng', raw)], port) == []


def test_codex_tabs_are_restored_from_the_raw_start_tags():
    raw = (b'<codex><character name="A" description="x \t\\n y"/>'
           b'<character name="B" description="no tab here"/>'
           b'<character name="C" description="&quot;q&quot;\ttab"/></codex>')
    root = ET.fromstring(raw)                                  # an XML parser turns each tab into a space
    assert root[0].get('description') == 'x  \\n y'
    assert F.attribute_tabs(raw, root, 'character', 'description') == 2
    assert root[0].get('description') == 'x \t\\n y'
    assert root[1].get('description') == 'no tab here'
    assert root[2].get('description') == '"q"\ttab'
    # a table whose start tags and parsed children disagree is left alone
    root = ET.fromstring(raw)
    assert F.attribute_tabs(raw + b'<character name="D" description="z"/>', root, 'character', 'description') == 0
    assert root[0].get('description') == 'x  \\n y'


# ------------------------------------------------------------------------------------------------ zoneinfo
ZONEINFO = ('<zoneinfo>'
            '<zone name="m\\m\\first" loading="l1" savename="Entrance"/>'
            '<zone name="m\\m\\first" loading="l2" savename="Conduit"/>'
            '<zone name="r\\r\\typo_in" savename="Island"/>'
            '<zone name="r\\r\\fine" savename="Fine"/></zoneinfo>')


def with_fixes(dup, typo):
    saved = Z.ZONEINFO_DUPLICATE_TARGETS, Z.ZONEINFO_NAME_TYPOS
    Z.ZONEINFO_DUPLICATE_TARGETS, Z.ZONEINFO_NAME_TYPOS = dup, typo
    try:
        return Z.x1_zoneinfo_entries(tree(ZONEINFO), ('m/m/first', 'm/m/second', 'r/r/real_in', 'r/r/fine'))
    finally:
        Z.ZONEINFO_DUPLICATE_TARGETS, Z.ZONEINFO_NAME_TYPOS = saved


def test_zoneinfo_duplicate_goes_to_its_target_and_typo_to_its_zone():
    entries, notes = with_fixes({'m/m/first': 'm/m/second'}, {'r/r/typo_in': 'r/r/real_in'})
    assert entries['m/m/first']['savename'] == 'Entrance'
    assert entries['m/m/second']['savename'] == 'Conduit' and entries['m/m/second']['loading'] == 'l2'
    assert entries['r/r/real_in']['savename'] == 'Island' and 'r/r/typo_in' not in entries
    assert entries['r/r/fine']['savename'] == 'Fine'
    assert len(notes) == 2


def test_zoneinfo_without_a_target_keeps_the_first_entry_and_reports():
    entries, notes = with_fixes({}, {})
    assert entries['m/m/first']['savename'] == 'Entrance' and 'm/m/second' not in entries
    assert 'r/r/typo_in' in entries and any('dropped' in n for n in notes)


def test_zoneinfo_repairs_never_overwrite_or_aim_at_unconverted_zones():
    entries, _ = Z.x1_zoneinfo_entries(tree(ZONEINFO), ('m/m/first',))      # target zones are not converted
    assert 'm/m/second' not in entries and 'r/r/typo_in' in entries
    own = ZONEINFO.replace('</zoneinfo>', '<zone name="m\\m\\second" savename="Own"/></zoneinfo>')
    saved = Z.ZONEINFO_DUPLICATE_TARGETS
    Z.ZONEINFO_DUPLICATE_TARGETS = {'m/m/first': 'm/m/second'}
    try:
        entries, _ = Z.x1_zoneinfo_entries(tree(own), ('m/m/first', 'm/m/second'))
    finally:
        Z.ZONEINFO_DUPLICATE_TARGETS = saved
    assert entries['m/m/second']['savename'] == 'Own'


def test_the_shipped_repairs_name_the_two_slips():
    assert Z.ZONEINFO_DUPLICATE_TARGETS == {'mount/mount/mount': 'mount/mount/mount2'}
    assert Z.ZONEINFO_NAME_TYPOS == {'muir_is/muir2/mui_in2': 'muir_is/muir2/muir_in2'}
    key = '/zoneinfo/zone[mount/mount/mount]~1'
    assert T.zoneinfo_repair_target(key) == 'mount/mount/mount2'
    assert T.zoneinfo_repair_target('/zoneinfo/zone[muir_is/muir2/mui_in2]') == 'muir_is/muir2/muir_in2'
    assert T.zoneinfo_repair_target('/zoneinfo/zone[mount/mount/mount]') is None


def test_a_repaired_zoneinfo_entry_counts_as_rewritten():
    x1 = '<zoneinfo><zone name="m\\m\\first" savename="E"/><zone name="m\\m\\first" savename="C"/></zoneinfo>'
    port = make_port({'data/zoneinfo.engb': '<zoneinfo><zone name="m/m/first" savename="E"/>'
                                           '<zone name="mount/mount/mount2" savename="C"/></zoneinfo>'})
    rows = one('data/zoneinfo.eng', x1, port)
    assert classes(rows) == [('shipped', ''), ('unaccounted', '')]       # a generic made-up name: no repair target
    x1 = x1.replace('m\\m\\first', 'mount\\mount\\mount')
    port = make_port({'data/zoneinfo.engb': '<zoneinfo><zone name="mount/mount/mount" savename="E"/>'
                                           '<zone name="mount/mount/mount2" savename="C"/></zoneinfo>'})
    assert classes(one('data/zoneinfo.eng', x1, port)) == [('shipped', ''), ('rewritten', 'zoneinfo-repair')]
    gone = make_port({'data/zoneinfo.engb': '<zoneinfo><zone name="mount/mount/mount" savename="E"/></zoneinfo>'})
    assert classes(one('data/zoneinfo.eng', x1, gone)) == [('shipped', ''), ('unaccounted', '')]


# ------------------------------------------------------------------------------------------------ build_zoneinfo wiring
class _ZoneCtx:
    def __init__(self, x1_xml, base_xml):
        self.x1_xml, self.base_xml, self.written, self.notes = x1_xml, base_xml, {}, []

    base_index = type('Idx', (), {'find': staticmethod(lambda stem, exts: None)})()

    def opt(self, key):
        return None

    def read_x1_xml(self, rel):
        return tree(self.x1_xml)

    def read_base_xmlb(self, rel):
        return tree(self.base_xml)

    def write_xmlb_pair(self, rel, xmlb, engb, source=None):
        self.written[rel] = (xmlb, engb)

    def note(self, m):
        self.notes.append(m)

    def warn(self, m):
        self.notes.append(m)

    def defer(self, m):
        self.notes.append(m)

    def error(self, m):
        raise AssertionError(m)


def test_build_zoneinfo_writes_the_repaired_entries():
    import collections
    ctx = _ZoneCtx(
        '<zoneinfo><zone name="mount\\mount\\mount" loading="textures/loading/one" savename="Entrance"/>'
        '<zone name="mount\\mount\\mount" loading="textures/loading/two" savename="Conduit"/>'
        '<zone name="muir_is\\muir2\\mui_in2" savename="Island"/></zoneinfo>',
        '<zoneinfo><zone name="other/x/y" act="1" build="normal" state="1"/></zoneinfo>')
    z = object.__new__(Z.Zones)
    z.ctx, z.counts, z.zone_acts = ctx, collections.Counter(), {}
    z.converted = ['mount/mount/mount', 'mount/mount/mount2', 'muir_is/muir2/muir_in2']
    z.prov = type('P', (), {'zone_act': staticmethod(lambda c, zone: 7)})()
    z.loading_ref = lambda v, where: None
    z.act_towncenters = lambda top, ext: {'added': {}, 'stripped': [], 'entries': 0, 'towncenters': {}}
    z.build_zoneinfo()
    xmlb, engb = ctx.written['Data/zoneinfo']
    got = {e.get('name'): e for e in engb}
    assert got['mount/mount/mount'].get('savename') == 'Entrance'
    assert got['mount/mount/mount'].get('loading') == 'textures/loading/one'
    assert got['mount/mount/mount2'].get('savename') == 'Conduit'
    assert got['mount/mount/mount2'].get('loading') == 'textures/loading/two'
    assert got['muir_is/muir2/muir_in2'].get('savename') == 'Island'
    assert 'muir_is/muir2/mui_in2' not in got
    assert z.counts['zoneinfo_x1_repaired'] == 2


# A converted Danger Room reward item (SPEC 21.3): its XML1 description is accounted for only when the port's item of
# that name carries exactly the enhancement descriptions frontend.translate_equipment makes (review 2026-10-25: V66
# had returned item-enhancements because the item existed). Invented item, invented wording.
X1_BELT = ('<inventory><item name="belt_of_test" type="equipment" description="placeholder_desc">'
           '<activepowerup powerup="strength" level="4"/><activepowerup powerup="speed" level="6"/></item></inventory>')


def _belt_port(enhancements, base=frozenset(('have',))):
    inner = ''.join(f'<enhancement description="{d}"><powerup life="-1"/></enhancement>' if d is not None
                    else '<enhancement><powerup life="-1"/></enhancement>' for d in enhancements)
    return make_port({'data/items.engb': f'<inventory><item name="belt_of_test" type="equipment">{inner}</item>'
                                         f'<item name="have" displayname="Theirs"/></inventory>'},
                     item_names=frozenset(('belt_of_test', 'have')), base_item_names=base)


def test_item_enhancements_are_checked_by_running_the_rule():
    assert classes(one('data/items.eng', X1_BELT, _belt_port(['+^%d Striking', '+^%d Speed']))) == [
        ('rewritten', 'item-enhancements')]


def test_removed_or_changed_item_descriptions_are_reported():
    for enh in ([], ['+^%d Striking'], [None, None], ['+^%d Striking', '+^%d Speed', '+^%d Body'],
                ['+^%d Striking', 'changed']):
        assert classes(one('data/items.eng', X1_BELT, _belt_port(enh))) == [('unaccounted', '')], enh


def test_an_xml2_item_keeps_its_own_text():
    # the same name in XML2's own Data/items: the builder keeps XML2's entry (item-table), whatever it carries
    assert classes(one('data/items.eng', X1_BELT, _belt_port([], base=frozenset(('have', 'belt_of_test'))))) == [
        ('xml2', 'item-table')]
