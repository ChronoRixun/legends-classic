"""SPEC 105: where every XML1 text string went (gap row C10).

Every text attribute of XML1's localized tables (`.eng`: conversations, subtitles, dialogs, menus, objectives, codex,
credits, trivia, Danger Room, zoneinfo, strings, items, herostat / npcstat / shared talents, fight styles, weapons ...)
is placed in exactly one class:

  shipped    the port's file for that table has the string under the same key, byte for byte
  moved      the string is byte-identical somewhere else in the port's text tables (regrouped by the builder:
             objectives per act, dialog platform variants, talents per hero, ...)
  rewritten  the port's text is derived from the XML1 text by a named builder rule (REWRITES), checked by running
             the rule: speaker tokens, value codes, menu-code escapes, the Danger Room outro trim, ...
  xml2       an XMen2.exe / XML2 table owns this text by design (POLICIES): the id-addressed string table, the PC
             menus, the item table, ...; XML1's string has no consumer in XMen2.exe
  dropped    XML1 text the port does not ship and has no consumer for (POLICIES): cut content, mission-select
             attributes, text of missions no script starts, ...
  unaccounted  none of the above: the validator's V66 reports it (a lost string)

The module is pure: it reads XML1 trees and the port's decoded text tables through the `Port` object and never
touches game files itself. It names keys, tags and attributes, never XML1 text.
"""
from __future__ import annotations

import collections
import re

# ------------------------------------------------------------------------------------------------ strings
TEXT_ATTRS = frozenset(('text', 'displayname', 'descname', 'description', 'updatedescription', 'savename', 'title',
                        'intro', 'outro', 'hint', 'info', 'movename', 'enttitle', 'desctext', 'desctext1', 'desctext2',
                        'desctext3', 'help2'))
CLASSES = ('shipped', 'moved', 'rewritten', 'xml2', 'dropped', 'unaccounted')
SKIP_PREFIXES = ('maps/',)                  # zone files: entity names, not text tables


def element_key(parent_key, el, counts):
    """Key of child `el` under `parent_key`: tag plus its name / id (lowercase), else its position among same-tag
    siblings. `counts` is the Counter of the parent's tags so far; a repeated identity gets '~n'."""
    name = (el.get('name') or el.get('id') or '').lower().replace('\\', '/')
    ident = el.tag + (f'[{name}]' if name else f'#{counts[el.tag]}')
    counts[el.tag] += 1
    return f'{parent_key}/{ident}'


def keyed_text(root, extra_name_attr=False):
    """{key: {attr: value}} of every element's text attributes (the key path uses tag + name/id identity)."""
    out = collections.OrderedDict()

    def put(key, el):
        k, i = key, 0
        while k in out:
            i += 1
            k = f'{key}~{i}'
        attrs = {a: v for a, v in el.attrib.items() if a in TEXT_ATTRS or (extra_name_attr and a == 'name')}
        out[k] = attrs
        return k

    def rec(el, key):
        counts = collections.Counter()
        for c in el:
            rec(c, put(element_key(key, c, counts), c))

    if root is None:
        return out
    if root.tag == '__multi__' or root.tag.startswith('__'):          # xmlb.MULTI_ROOT
        counts = collections.Counter()
        for c in root:
            rec(c, put(element_key('', c, counts), c))
    else:
        rec(root, put('/' + root.tag, root))
    return out


def strings_of(rel, root):
    """[(key, attr, value)] of the text attributes of XML1 table `rel` (lowercase rel, e.g. 'data/credits.eng')."""
    extra = rel == 'data/review_paths.eng'
    rows = []
    for key, attrs in keyed_text(root, extra).items():
        for a, v in attrs.items():
            rows.append((key, a, v))
    return rows


def port_rels(rel):
    """Candidate port tables for XML1 `rel` ('x.eng' -> 'x.engb'; dialogs also under dialogs/x1/)."""
    base = rel[:-4] if rel.endswith('.eng') else rel
    out = [base + '.engb']
    if rel.startswith('dialogs/'):
        out.append('dialogs/x1/' + base[len('dialogs/'):] + '.engb')
    return out


# ------------------------------------------------------------------------------------------------ the port side
class Port:
    """The port's decoded text tables. `trees` is {lowercase rel: Element} of every text table the build wrote under
    Data/, Conversations/, Dialogs/, Subtitles/, Movies/ and UI/Menus/ (the `.engb` halves); `facts` carries what
    the rules need from the build (see DEFAULT_FACTS)."""

    def __init__(self, trees, facts=None):
        self.trees = trees
        self.facts = dict(DEFAULT_FACTS, **(facts or {}))
        self.x1_items = {}          # {lowercase name: XML1 <item>} of the traced data/items.eng (trace() fills it)
        self._keyed = {}
        self._values = None

    def keyed(self, rel):
        if rel not in self._keyed:
            self._keyed[rel] = keyed_text(self.trees[rel], rel == 'data/review_paths.engb') if rel in self.trees else None
        return self._keyed[rel]

    @property
    def values(self):
        """every attribute value of every table (the 'byte-identical somewhere' test)."""
        if self._values is None:
            vals = set()
            for root in self.trees.values():
                for el in root.iter():
                    vals.update(el.attrib.values())
            self._values = vals
        return self._values

    def primary(self, rel):
        for r in port_rels(rel):
            if r in self.trees:
                return r
        return None


DEFAULT_FACTS = {
    'unused_missions': frozenset(),         # mission files no script starts (research/scripts/mission_plan.json)
    'item_names': frozenset(),              # lowercase item names of the port's Data/items
    'base_item_names': None,                # lowercase item names of XML2's own Data/items (None: not read, then
                                            # every port item counts as XML2's for the item-table policy)
    'talent_names': frozenset(),            # lowercase talent names of every port talent table
    'converted_zones': frozenset(),
    'x1_values': None,                      # heroes.Values of XML1's values.xml
}

# ------------------------------------------------------------------------------------------------ rewrite rules
# id -> what the builder does and where it is specified. A rule is verified by running it (see _rule_*), never by
# listing strings.
REWRITES = {
    'speaker-token': 'conversation speaker tokens renamed to the port\'s stats entries (%ALISON% -> %MAGMA% / '
                     '%ALISON_SCRIPTED%, %FROST% -> %EMMA%, %HERO% -> %HERO_X1DOUBLE% / %HERO_SCRIPTED%); wording and '
                     'voice file unchanged (SPEC 12.1, 18.1; scripts.SPEAKER_TOKEN_ALIASES, scripts_transform)',
    'value-codes': 'XML1 value codes (^L3, ^P1, BADREF keys) resolved to the numbers XMen2.exe cannot compute '
                   '(heroes.Values.resolve_text / badref_text; SPEC 24)',
    'menu-code-escape': 'credit and trivia texts: # $ ~ | written as |c because XMen2.exe\'s text renderer reads them '
                        'as codes (frontend.escape_menu_text; SPEC 21.4.1)',
    'extra-credit-trim': 'Danger Room FR106 outro keeps "Well Done!" only: the extra-credit marks are default.xbe '
                         'logic the port does not have and their glyphs { | } ~ are renderer codes in XMen2.exe '
                         '(frontend._trim_extra_credit; SPEC 21.3)',
    'zoneinfo-repair': 'XML1 zoneinfo slips repaired: a repeated name, a name no zone file has (zones.'
                       'x1_zoneinfo_entries; SPEC 105)',
    'item-enhancements': 'a Danger Room reward item\'s description split into one description per enhancement with '
                         'the port\'s stat scale (frontend.translate_equipment; SPEC 21.3)',
}

SPEAKER_RENAMES = {('alison', 'magma'), ('frost', 'emma')}
SPEAKER_SUFFIXES = ('_x1double', '_scripted')
_TOKEN = re.compile(r'%[^%\s]+%')
_WHITESPACE = re.compile('[\t\r\n]')


def speaker_rewrite(old, new):
    """True when `new` is `old` with only speaker tokens renamed by the builder (pure)."""
    a, b = _TOKEN.findall(old), _TOKEN.findall(new)
    if len(a) != len(b) or _TOKEN.sub('@', old) != _TOKEN.sub('@', new):
        return False
    for x, y in zip(a, b):
        x, y = x.strip('%').lower(), y.strip('%').lower()
        if x == y or (x, y) in SPEAKER_RENAMES or y in tuple(x + s for s in SPEAKER_SUFFIXES):
            continue
        if x == 'alison' and y == 'alison_scripted':
            continue
        return False
    return True


def _frontend():
    from . import frontend
    return frontend


def _heroes():
    from . import heroes
    return heroes


def expand_value_codes(value, values):
    """The port text of an XML1 description with value codes (pure given `values`, a heroes.Values or None)."""
    if values is None:
        return None
    H = _heroes()
    try:
        return values.resolve_text(H.badref_text(value))
    except KeyError:
        return None


# ------------------------------------------------------------------------------------------------ policies
# (id, matcher, class, reason). The matcher is (rel, key, attr, value, port) -> bool and looks at structure only.
CUT_CONVERSATIONS = frozenset(('conversations/nyc/riots/3_2_6.eng',))     # SPEC 105: the cut reply (zone absent in XML1)
MENU_PREFIX = 'ui/menus/'
POWER_STYLE_PREFIXES = ('data/fightstyles/', 'data/powerstyles/')


def _in_mission(rel):
    return rel.startswith('data/missions/')


def _mission_name(rel):
    return rel.rsplit('/', 1)[-1][:-4]


def _item_name(key):
    m = re.search(r'/item\[([^\]]+)\]', key)
    return m.group(1) if m else ''


def _talent_name(key):
    m = re.search(r'/Talent\[([^\]]+)\]', key)
    return m.group(1) if m else ''


POLICIES = (
    ('cut-conversation', 'dropped',
     'a conversation reply the port removes: it starts a side mission in a zone neither XML1 nor XML2 has (SPEC 105)',
     lambda rel, key, attr, v, port: rel in CUT_CONVERSATIONS),
    ('strings-by-id', 'xml2',
     'XMen2.exe addresses Data/strings by its own ids; XML1\'s ids were read by default.xbe only and no XML1 data '
     'names one (SPEC 4.4)',
     lambda rel, key, attr, v, port: rel == 'data/strings.eng'),
    ('pc-menus', 'xml2',
     'the PC menus are XMen2.exe\'s own classes with its own labels; XML1\'s menus lend artwork only (SPEC 21)',
     lambda rel, key, attr, v, port: rel.startswith(MENU_PREFIX)),
    ('item-table', 'xml2',
     'an item XML2 already has keeps XML2\'s name and text (SPEC 11.3)',
     lambda rel, key, attr, v, port: rel == 'data/items.eng' and _xml2_item(_item_name(key), port)),
    ('item-not-added', 'dropped',
     'XML1 items no converted content names are not added; the loot work (G8 / E2) owns them (SPEC 11.3)',
     lambda rel, key, attr, v, port: rel == 'data/items.eng' and _item_name(key) not in port.facts['item_names']),
    ('weapons-table', 'dropped',
     'XMen2.exe has no weapons table: XML1 weapons live on as style triggers (SPEC 29)',
     lambda rel, key, attr, v, port: rel.startswith('data/weapons/')),
    ('move-names', 'dropped',
     'fight-move names: XMen2.exe shows none and XML2\'s own styles carry almost none (XML2 wins a shared name, '
     'SPEC 4.4)',
     lambda rel, key, attr, v, port: rel.startswith(POWER_STYLE_PREFIXES) or rel == 'data/shared_nodes.eng'),
    ('unused-shared-talent', 'dropped',
     'a shared talent no XML1 hero or enemy lists, or a fight-style unlock whose text XMen2.exe never shows '
     '(fight-style talents carry none in XML2 either)',
     lambda rel, key, attr, v, port: rel == 'data/shared_talents.eng' and (
         _talent_name(key).startswith('fightstyle_') or _talent_name(key) not in port.facts['talent_names'])),
    ('mission-select', 'dropped',
     'MISSION descname / description fed XML1\'s mission chooser; XMen2.exe\'s MISSION has no text (SPEC 37)',
     lambda rel, key, attr, v, port: _in_mission(rel) and key.count('/') == 1),
    ('unused-mission', 'dropped',
     'objective of a mission file no script starts (mission_plan unused_mission_files)',
     lambda rel, key, attr, v, port: _in_mission(rel) and _mission_name(rel) in port.facts['unused_missions']),
)


def _rule(rel, key, attr, value, pv, port):
    """The id of the REWRITES rule that turns XML1 `value` into the port text (`pv`, the text at the same key or
    None), or None."""
    if rel.startswith('conversations/') and pv is not None and speaker_rewrite(value, pv):
        return 'speaker-token'
    if rel in ('data/credits.eng', 'data/trivia.eng'):
        want = _frontend().escape_menu_text(value)
        if want != value and (want == pv or want in port.values):
            return 'menu-code-escape'
    if rel == 'data/dangerroom.eng' and attr == 'outro':
        want = _frontend()._trim_extra_credit(value)
        if want != value and (want == pv or want in port.values):
            return 'extra-credit-trim'
    if rel == 'data/zoneinfo.eng' and attr == 'savename':
        target = zoneinfo_repair_target(key)
        pz = port.primary(rel)
        q = port.keyed(pz) if pz else None
        if target and q and q.get(f'/zoneinfo/zone[{target}]', {}).get('savename') == value:
            return 'zoneinfo-repair'
    if '^' in value or value.startswith('BADREF:'):
        want = expand_value_codes(value, port.facts['x1_values'])
        if want is not None and want != value and (want == pv or want in port.values):
            return 'value-codes'
    if rel == 'data/items.eng' and attr == 'description' and _converted_item(_item_name(key), port) \
            and item_enhancements_match(_item_name(key), port):
        return 'item-enhancements'
    return None


def _xml2_item(name, port):
    """True when the port's item `name` is XML2's own (kept by the builder), not one it added from XML1."""
    base = port.facts['base_item_names']
    return name in port.facts['item_names'] and (base is None or name in base)


def _converted_item(name, port):
    return name in port.facts['item_names'] and not _xml2_item(name, port)


def item_enhancements_match(name, port):
    """The item-enhancements rule, run: XML1's item `name` translated by frontend.translate_equipment gives
    enhancement descriptions, and the port's item of that name carries exactly those, none empty. A converted item
    whose descriptions are missing or changed is therefore not explained by the rule (V66 reports it)."""
    x1 = port.x1_items.get(name)
    if x1 is None:
        return False
    el, _note = _frontend().translate_equipment(None, x1)
    if el is None:
        return False
    want = [e.get('description') for e in el.findall('enhancement')]
    root = port.trees.get('data/items.engb')
    got = None
    for it in (root.iter('item') if root is not None else ()):
        if (it.get('name') or '').lower() == name:
            got = [e.get('description') for e in it.findall('enhancement')]
            break
    return bool(want) and all(want) and got == want


# Tables whose strings must stay under their own key: a repeated or generic text elsewhere in the port is no proof
# (zone labels, credits, ...). The other tables are regrouped by the builder (objectives per act, talents per hero,
# dialog platform variants) and are matched by text.
STRICT_TABLES = frozenset(('data/zoneinfo.eng', 'data/credits.eng', 'data/trivia.eng', 'data/dangerroom.eng',
                           'data/codex.eng', 'data/review_paths.eng'))
STRICT_PREFIXES = ('subtitles/', 'movies/', 'data/personal/')


def is_strict(rel):
    return rel in STRICT_TABLES or rel.startswith(STRICT_PREFIXES)


def zoneinfo_repair_target(key):
    """The zone a zoneinfo entry key was repaired onto (zones.ZONEINFO_*), or None."""
    from . import zones as Z
    m = re.search(r'zone\[([^\]]*)\](~\d+)?$', key)
    if not m:
        return None
    if m.group(2):
        return Z.ZONEINFO_DUPLICATE_TARGETS.get(m.group(1))
    return Z.ZONEINFO_NAME_TYPOS.get(m.group(1))


def port_key(rel, key):
    """The key the port files an XML1 key under: only the codex renames one entry (frontend.CODEX_NAME_MAP)."""
    if rel == 'data/codex.eng':
        for old, (new, _why) in _frontend().CODEX_NAME_MAP.items():
            key = key.replace(f'character[{old}]', f'character[{new.lower()}]')
    return key


def classify(rel, key, attr, value, port):
    """(class, rule-or-policy id, port file or '') of one XML1 string (pure given `port`)."""
    pf = port.primary(rel)
    q = port.keyed(pf) if pf else None
    pk = port_key(rel, key)
    pv = q[pk].get(attr) if q is not None and pk in q else None
    if pv is not None and (pv == value or _WHITESPACE.sub(' ', pv) == value):     # XML1's reader turned tabs into spaces
        return 'shipped', '', pf
    r = _rule(rel, key, attr, value, pv, port)
    if r:
        return 'rewritten', r, pf or ''
    if value in port.values and not is_strict(rel):
        return 'moved', '', pf or ''
    for pid, cls, _why, match in POLICIES:
        if match(rel, key, attr, value, port):
            return cls, pid, pf or ''
    return 'unaccounted', '', pf or ''


Row = collections.namedtuple('Row', 'rel key attr value cls rule pfile')


def trace(tables, port):
    """[Row] for every string of `tables` ([(rel, root)]; lowercase rels). Zone files are skipped."""
    rows = []
    for rel, root in tables:
        if rel.startswith(SKIP_PREFIXES) or root is None:
            continue
        if rel == 'data/items.eng':
            port.x1_items = {(el.get('name') or '').lower(): el for el in root.iter('item') if el.get('name')}
        for key, attr, value in strings_of(rel, root):
            cls, rule, pf = classify(rel, key, attr, value, port)
            rows.append(Row(rel, key, attr, value, cls, rule, pf))
    return rows


def table_group(rel):
    """The report class of a table: 'conversations', 'data/credits.eng', 'data/missions', 'ui' ..."""
    if rel.startswith('data/'):
        if rel.startswith('data/missions/'):
            return 'data/missions'
        return '/'.join(rel.split('/')[:2]) if rel.count('/') > 1 else rel
    return rel.split('/')[0]


def summarize(rows):
    """{group: Counter(class)} plus {(class, rule): n}."""
    by_group = collections.defaultdict(collections.Counter)
    by_rule = collections.Counter()
    for r in rows:
        by_group[table_group(r.rel)][r.cls] += 1
        if r.rule:
            by_rule[(r.cls, r.rule)] += 1
    return by_group, by_rule


def reasons():
    """{id: sentence} of every rule and policy (the table's legend)."""
    out = dict(REWRITES)
    for pid, _cls, why, _m in POLICIES:
        out[pid] = why
    return out


# ------------------------------------------------------------------------------------------------ validator (V66)
PORT_TABLE_PREFIXES = ('data/', 'conversations/', 'dialogs/', 'subtitles/', 'movies/', 'ui/menus/')
FRONTEND_TABLES = frozenset(('data/credits.eng', 'data/trivia.eng', 'data/dangerroom.eng', 'data/codex.eng',
                             'data/review_paths.eng'))
UNACCOUNTED_SHOWN = 12
_RAW_ATTR = re.compile(rb'([A-Za-z_][\w.\-]*)\s*=\s*"([^"]*)"')


def raw_whitespace_values(raw):
    """[text] of the attribute values in the raw XML1 bytes `raw` that hold a tab, CR or LF: an XML parser turns
    each into a space (the builder's reader does), so only the raw bytes can show it. Pure."""
    import html
    return [html.unescape(m.group(2).decode('latin-1')) for m in _RAW_ATTR.finditer(raw)
            if re.search(rb'[\t\r\n]', m.group(2))]


def lost_whitespace(raw_tables, port):
    """[(rel, text)] of raw attribute values with a tab / CR / LF that the port does not carry unchanged."""
    out = []
    for rel, raw in raw_tables:
        for text in raw_whitespace_values(raw):
            if text not in port.values:
                out.append((rel, text))
    return out


def port_trees_from(v):
    """{rel: Element} of the port's `.engb` text tables, read through the validator `v` (out index + decoder)."""
    trees = {}
    for rel in v.idx.keys():
        if rel.endswith('.engb') and rel.startswith(PORT_TABLE_PREFIXES):
            t = v.tree(rel)
            if t is not None:
                trees[rel] = t
    return trees


def facts_from(ctx, trees):
    """The rules' build facts (DEFAULT_FACTS) read from the context and the port's tables."""
    unused = frozenset()
    try:
        unused = frozenset(ctx.research_json('scripts/mission_plan.json').get('unused_mission_files') or ())
    except (KeyError, OSError, ValueError):
        pass
    items = frozenset((el.get('name') or '').lower() for el in trees['data/items.engb'].iter('item')) \
        if 'data/items.engb' in trees else frozenset()
    # XML2's own items: the builder keeps them and appends only the XML1 items XML2 lacks (zones.items_to_add)
    from . import common as C
    base_items = set()
    for ext in ('.XMLB', '.engb'):
        try:
            if ctx.base_exists(f'Data/items{ext}'):
                base_items |= {(c.get('name') or '').lower() for c in C.iter_roots(ctx.read_base_xmlb(
                    f'Data/items{ext}'))[0] if c.get('name')}
        except (KeyError, OSError, ValueError):
            pass
    talents = set()
    for rel, root in trees.items():
        if rel.startswith('data/talents/') or rel in ('data/shared_talents.engb', 'data/herostat.engb',
                                                      'data/npcstat.engb'):
            talents.update((el.get('name') or '').lower() for el in root.iter() if el.tag.lower() == 'talent')
    return {'unused_missions': unused, 'item_names': items, 'base_item_names': frozenset(base_items),
            'talent_names': frozenset(talents),
            'x1_values': ctx.x1_values()}


def x1_tables_from(ctx, skip_frontend=False):
    """[(rel, Element)] of every XML1 `.eng` table outside maps/ (the builder's own reader)."""
    out = []
    for rel in ctx.x1_rels():
        if not rel.endswith('.eng') or rel.startswith(SKIP_PREFIXES):
            continue
        if skip_frontend and rel in FRONTEND_TABLES:
            continue
        try:
            root = ctx.read_x1_xml(rel)
        except (KeyError, ValueError, OSError):
            continue
        if root is not None:
            out.append((rel, root))
    return out


def validate(v, ck):
    """V66 text coverage (SPEC 105): every text string of XML1's localized tables is shipped, moved, rewritten by a
    named rule, owned by XML2 by design, or dropped for a stated reason. An unaccounted string is an error."""
    from . import common as C
    ctx = v.ctx
    xml1_front = C.frontend_mode(ctx) == 'xml1'
    trees = port_trees_from(v)
    if not trees:
        ck.note('no port text tables to compare')
        return
    port = Port(trees, facts_from(ctx, trees))
    rows = trace(x1_tables_from(ctx, skip_frontend=not xml1_front), port)
    by_group, by_rule = summarize(rows)
    for cls in CLASSES:
        ck.set(f'text_{cls}', sum(1 for r in rows if r.cls == cls))
    for (cls, rule), n in sorted(by_rule.items()):
        ck.set(f'text_{cls}_{rule}'.replace('-', '_'), n)
    lost = [r for r in rows if r.cls == 'unaccounted']
    raws = []
    for rel, _root in x1_tables_from(ctx, skip_frontend=not xml1_front):
        p = ctx.x1_path(rel)
        if p is not None and rel.startswith('data/'):
            raws.append((rel, p.read_bytes()))
    ws = lost_whitespace(raws, port)
    ck.set('text_whitespace_lost', len(ws))
    for rel, _text in ws[:UNACCOUNTED_SHOWN]:
        ck.error(f'{rel}: an XML1 text holds a tab / line break that the port copy lacks (an XML parser turns it '
                 f'into a space)')
    for r in lost[:UNACCOUNTED_SHOWN]:
        ck.error(f'{r.rel} {r.key} {r.attr}: an XML1 string is not in the build and no rule or policy explains it')
    if len(lost) > UNACCOUNTED_SHOWN:
        ck.error(f'... and {len(lost) - UNACCOUNTED_SHOWN} more unaccounted XML1 strings')
    if not xml1_front:
        ck.note('--frontend xml2: XML2\'s credits, trivia, Danger Room, codex and Review tables are kept (not compared)')
