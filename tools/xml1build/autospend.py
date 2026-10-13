"""xml1build.autospend - XML1's automatic stat growth in Data/autospend.XMLB (SPEC 94).

The first game grants an automatic stat bonus on each level 2..40 from stat_rules.xml: every hero names a
template class (bruiser or support, `<CHARACTER name=.. template=..>`) and each listed level applies its bonus
stats at once (default.xbe 0xaed70 / 0xaea90). Nothing is applied above level 40. The port's units are
body / mind / strength x4 (heroes.STAT_SCALE) and speed x2 (heroes.SPEED_MAP).

XMen2.exe grants no such table; on each level gained it walks the hero's Data/autospend.XMLB class
(0x4bbae0 -> 0x43cf90 -> 0x43d000), looked up by the herostat `autospend` name:
- the parser (0x43d0c0) fills a static table of FOUR class records (0x34 bytes each, from 0x712bf4); every
  CharacterClass after the fourth is skipped (cmp [ebx+0x78],4 at 0x43d18d), and a hero whose class was skipped
  gets no growth at all (0x43cf90 finds no record and returns);
- a record holds up to four 6-byte rules from +0x14 (start, rate, four signed stat deltas; the rule adder
  0x43d370 drops a fifth <bonus>, cmp [ecx+0x30],4 at 0x43d373);
- a rule fires on level L when L == start, or L > start, rate > 0 and (L - start) % rate == 0 (so rate 0 fires
  once, at start), adding its deltas to the stat's class-bonus byte (CStats+0x10; reversed on a level lost);
- the class attributes body / mind / speed / strength are the auto-spend weights of the unspent points
  (normalized by the engine, 0x43d24d).
The record cannot express a cap level, so past 40 the periodic rules keep firing up to the level cap (45 with
[Game] XPCurve=xml1) and the curve drifts from XML1's flat line.

This module puts two classes, x1_bruiser / x1_support, FIRST in the built file (only the first four load), keeps
XML2's classes the built herostat still names, and drops the rest. Their rules are a fixed approximation of the
templates' per-level tables (X1_RULES; V-H17 measures the deviation against the player's own stat_rules.xml at
build time). XML1's `spend` lists (the suggested spend of the unspent point) are read from the same file and
become the classes' auto-spend weights; XML1's `agility` suggestions count as speed, the closest port stat.
No XML1 table is stored here: everything XML1-specific is read from the player's disc when the build runs.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter

CLASS_LIMIT = 4                # XMen2.exe 0x43d18d: cmp [ebx+0x78],4 - the parser skips every further CharacterClass
RULES_PER_CLASS = 4            # XMen2.exe 0x43d373 (rule adder 0x43d370): cmp [ecx+0x30],4 - a fifth <bonus> is dropped
AMOUNT_MAX = 127               # the four deltas are signed bytes (0x43d076 imul byte ptr)
BYTE_MAX = 255                 # start and rate are unsigned bytes (0x43d041 / 0x43d049)
FIRST_LEVEL = 2                # stat_rules.xml: a <level> without `offset` follows the previous one; the first is 2
LAST_X1_LEVEL = 40             # stat_rules.xml lists levels 2..40; nothing above
X1_TEMPLATES = {'bruiser': 'x1_bruiser', 'support': 'x1_support'}      # stat_rules.xml template -> our class
STAT_SCALE = {'body': 4, 'mind': 4, 'strength': 4, 'speed': 2}          # heroes.STAT_SCALE / SPEED_MAP slope
STATS = ('body', 'mind', 'speed', 'strength')
SPEND_ALIASES = {'agility': 'speed'}          # XML1's agility suggestion has no port stat; speed is the closest

# The fitted rules (start, rate, {stat: amount}): least per-level deviation from the templates' cumulative tables
# under the four-rule limit (hill-climbed over joint four-stat rules; SPEC 94). Rate 0 fires once, at start.
X1_RULES = {
    'x1_bruiser': [
        (2, 2, {'body': 4}),
        (3, 4, {'strength': 4}),
        (5, 5, {'speed': 2}),
        (5, 4, {'mind': 4}),
    ],
    'x1_support': [
        (2, 1, {'mind': 3}),
        (7, 4, {'strength': 4}),
        (5, 5, {'speed': 2}),
        (6, 0, {'body': 4, 'mind': -1}),
    ],
}

# Largest allowed per-level deviation (port points, levels 2..40) from the cumulative table the player's
# stat_rules.xml gives, per class and stat - the fit's worst error (V-H17 recomputes it at build time).
X1_MAX_DEV = {
    'x1_bruiser': {'body': 4, 'strength': 4, 'speed': 2, 'mind': 4},
    'x1_support': {'mind': 5, 'strength': 4, 'speed': 2, 'body': 0},
}


def fires(start, rate, level):
    """How many times a rule has fired by `level` (XMen2.exe 0x43d041..0x43d05f)."""
    if level < start:
        return 0
    if rate == 0:
        return 1
    return (level - start) // rate + 1


def cumulative(rules, level):
    """{stat: granted bonus points} the rules give a hero reaching `level` by the engine's walk (0x43d000):
    each rule adds its deltas once per fire level <= level; a level lost re-runs the walk with the sign reversed."""
    out = {s: 0 for s in STATS}
    for start, rate, amounts in rules:
        n = fires(start, rate, level)
        for stat, amount in amounts.items():
            out[stat] += amount * n
    return out


def x1_templates(root):
    """stat_rules.xml (the player's copy) -> ({template: {'bonus': {stat: [levels]}, 'spend': Counter}},
    {hero name lower: template}). A <level> without `offset` is the level after the previous one (the first: 2)."""
    templates, heroes = {}, {}
    if root is None:
        return templates, heroes
    for ch in root:
        if ch.tag.lower() != 'character':
            continue
        name = (ch.get('name') or '').lower()
        if ch.get('template'):
            heroes[name] = ch.get('template').lower()
            continue
        bonus, spend, level = {}, Counter(), FIRST_LEVEL - 1
        for lv in ch:
            if lv.tag.lower() != 'level':
                continue
            level = int(lv.get('offset')) if lv.get('offset') is not None else level + 1
            for b in lv:
                item = (b.get('item') or '').lower()
                if b.tag.lower() == 'bonus' and item in STAT_SCALE:
                    bonus.setdefault(item, []).extend([level] * int(b.get('level') or 1))
                elif b.tag.lower() == 'spend':
                    item = SPEND_ALIASES.get(item, item)
                    if item in STAT_SCALE:
                        spend[item] += int(b.get('level') or 1)
        templates[name] = {'bonus': bonus, 'spend': spend}
    return templates, heroes


def x1_cumulative(template, level):
    """{stat: bonus} a parsed template grants by `level`, in port units (x4 body/mind/strength, x2 speed);
    flat above LAST_X1_LEVEL as in XML1."""
    out = {s: 0 for s in STATS}
    for stat, levels in template['bonus'].items():
        out[stat] = STAT_SCALE[stat] * sum(1 for lv in levels if lv <= level)
    return out


def _class_element(cls, weights):
    el = ET.Element('CharacterClass', {'name': cls, **{s: str(weights.get(s, 0)) for s in STATS}})
    for start, rate, amounts in X1_RULES[cls]:
        attrs = {'start': str(start), 'rate': str(rate)}
        for stat in STATS:
            if amounts.get(stat):
                attrs[stat] = str(amounts[stat])
        ET.SubElement(el, 'bonus', attrs)
    return el


def set_x1_classes(root, templates, keep=()):
    """Put x1_bruiser / x1_support first in the AutoSpend tree, then XML2's classes named in `keep` (those the built
    herostat still uses), and drop everything past CLASS_LIMIT (the engine never loads it). True when the tree
    changed. Raises ValueError when a kept class cannot fit."""
    before = ET.tostring(root)
    classes = [c for c in root if c.tag == 'CharacterClass']
    others = [c for c in root if c.tag != 'CharacterClass']
    by_name = {(c.get('name') or '').lower(): c for c in classes}
    fresh = []
    for tmpl, cls in X1_TEMPLATES.items():
        weights = templates.get(tmpl, {}).get('spend') or {}
        fresh.append(_class_element(cls, weights))
    keep = {k.lower() for k in keep} - set(X1_TEMPLATES.values())
    kept = [c for n, c in by_name.items() if n in keep]                  # file order
    missing = sorted(k for k in set(keep) if k not in by_name)
    if missing:
        raise ValueError(f'autospend classes {missing} are named by herostat but not in Data/autospend.XMLB')
    if len(fresh) + len(kept) > CLASS_LIMIT:
        raise ValueError(f'{len(fresh) + len(kept)} autospend classes needed; XMen2.exe loads {CLASS_LIMIT} (0x43d18d)')
    for c in list(root):
        root.remove(c)
    for c in fresh + kept + others:
        root.append(c)
    return ET.tostring(root) != before


def used_classes(herostat_roots):
    """Lowercase autospend class names the herostat trees name."""
    out = set()
    for r in herostat_roots:
        if r is None:
            continue
        for el in r.iter():
            v = (el.get('autospend') or '').lower()
            if v:
                out.add(v)
    return out


def problems(root, templates, heroes=None, hero_classes=None, used=()):
    """V-H17 for the built Data/autospend.XMLB: x1_bruiser / x1_support and every class herostat names are among the
    first CLASS_LIMIT classes (the rest never load), the rules are the fitted ones within the format's limits, the
    simulated growth stays within the documented deviation from the player's stat_rules.xml at every level 2..40,
    the auto-spend weights are XML1's spend counts, and every hero stat_rules.xml names sits on its template's class
    (`heroes`: stat_rules hero -> template; `hero_classes`: herostat hero -> class)."""
    out = []
    classes = [c for c in root.iter('CharacterClass')]
    loaded = {(c.get('name') or '').lower(): c for c in classes[:CLASS_LIMIT]}
    if len(classes) > CLASS_LIMIT:
        out.append(f'{len(classes)} CharacterClass entries; XMen2.exe loads the first {CLASS_LIMIT} (0x43d18d), '
                   f'skips {[c.get("name") for c in classes[CLASS_LIMIT:]]}')
    for name in sorted(set(used)):
        if name not in loaded:
            out.append(f'herostat names autospend {name!r}, not among the {CLASS_LIMIT} classes XMen2.exe loads')
    for tmpl, cls in X1_TEMPLATES.items():
        el = loaded.get(cls)
        if el is None:
            out.append(f'{cls}: not among the first {CLASS_LIMIT} classes of Data/autospend.XMLB (never loaded)')
            continue
        template = templates.get(tmpl)
        if template is None:
            out.append(f'{cls}: stat_rules.xml has no template {tmpl!r}')
            continue
        bonus = [b for b in el if b.tag.lower() == 'bonus']
        if len(bonus) > RULES_PER_CLASS:
            out.append(f'{cls}: {len(bonus)} bonus rules; XMen2.exe keeps {RULES_PER_CLASS} (0x43d373)')
        actual = []
        for b in bonus:
            try:
                start, rate = int(b.get('start')), int(b.get('rate'))
                amounts = {s: int(b.get(s)) for s in STATS if b.get(s) is not None and int(b.get(s))}
            except (TypeError, ValueError):
                out.append(f'{cls}: bonus rule {b.attrib} is not numeric')
                continue
            if not (1 <= start <= BYTE_MAX and 0 <= rate <= BYTE_MAX):
                out.append(f'{cls}: bonus rule {b.attrib} start/rate outside an unsigned byte (start >= 1)')
            if any(abs(a) > AMOUNT_MAX for a in amounts.values()):
                out.append(f'{cls}: bonus rule {b.attrib} amount outside a signed byte')
            actual.append((start, rate, amounts))
        if actual != X1_RULES[cls]:
            out.append(f'{cls}: bonus rules {actual} != the fitted {X1_RULES[cls]}')
        for level in range(FIRST_LEVEL, LAST_X1_LEVEL + 1):
            got, want = cumulative(actual, level), x1_cumulative(template, level)
            for stat in STATS:
                dev = abs(got[stat] - want[stat])
                if dev > X1_MAX_DEV[cls][stat]:
                    out.append(f'{cls}: {stat} at level {level} deviates {dev} port points from stat_rules.xml '
                               f'(got {got[stat]}, want {want[stat]}, allowed {X1_MAX_DEV[cls][stat]})')
        weights = {s: int(el.get(s) or 0) for s in STATS}
        if weights != {s: template['spend'].get(s, 0) for s in STATS}:
            out.append(f'{cls}: auto-spend weights {weights} != stat_rules.xml spend counts {dict(template["spend"])}')
    for hero, tmpl in (heroes or {}).items():
        want = X1_TEMPLATES.get(tmpl)
        got = (hero_classes or {}).get(hero)
        if hero_classes is not None and got is not None and got != want:
            out.append(f'{hero}: herostat autospend {got!r}, stat_rules.xml template {tmpl!r} -> {want!r}')
    return out


# ---- The class each hero had before SPEC 94, for XML2 Fix's one-time re-base of saved class bonuses
#
# Saves written by builds before SPEC 94 hold the class bonus XML2's ratings classes gave (heroes.AUTOSPEND before
# SPEC 94, below, on the player's own XML2 Data/autospend.XMLB, which those builds shipped unchanged), plus anything
# else that writes the same bytes (the Review comics' stat rewards, 0x5d0920 -> 0x43a620). XML2 Fix 1.5 re-bases a
# save once on load (header optional bit 3): per hero, saved bonus - what its old class gave up to its processed level
# + what its current class gives, so the comic rewards stay. It needs the old classes, which this build no longer
# ships (only four classes load), so the build writes them here: LEGACY_REL, one line per hero.
LEGACY_AUTOSPEND = {'wolverine': 'bruiser', 'rogue': 'bruiser', 'colossus': 'bruiser',
                    'beast': 'bruiser_light', 'nightcrawler': 'bruiser_light', 'psylocke': 'bruiser_light',
                    'frost': 'support', 'phoenix': 'support', 'storm': 'support', 'profxastral': 'support',
                    'profxgladiator': 'support',
                    'cyclops': 'support_heavy', 'gambit': 'support_heavy', 'iceman': 'support_heavy',
                    'jubilee': 'support_heavy', 'magma': 'support_heavy'}
LEGACY_REL = 'Data/lcsave/autogrowth-legacy.txt'
LEGACY_MAGIC = 'autogrowth-legacy 1'
RECORD_ORDER = ('strength', 'speed', 'body', 'mind')      # the record's delta bytes = class-bonus bytes CStats+0x10..0x13


def engine_classes(root):
    """{class name lower: [(start, rate, (strength, speed, body, mind))]} as XMen2.exe loads an AutoSpend tree: the
    first CLASS_LIMIT classes, the first RULES_PER_CLASS rules each, a missing number 0."""
    out = {}
    for c in [c for c in root if c.tag == 'CharacterClass'][:CLASS_LIMIT]:
        rules = []
        for b in [b for b in c if b.tag.lower() == 'bonus'][:RULES_PER_CLASS]:
            rules.append((int(b.get('start') or 0), int(b.get('rate') or 0),
                          tuple(int(b.get(s) or 0) for s in RECORD_ORDER)))
        out[(c.get('name') or '').lower()] = rules
    return out


def legacy_text(stock_root, mapping=None):
    """LEGACY_REL's text: a magic line, then `hero<TAB>class<TAB>start,rate,strength,speed,body,mind;...` per hero of
    `mapping` (default LEGACY_AUTOSPEND), from the player's unmodified XML2 AutoSpend tree. Raises ValueError when a
    class is not among the four XMen2.exe loaded (it would never have given anything)."""
    classes = engine_classes(stock_root)
    lines = [LEGACY_MAGIC]
    for hero, cls in sorted((mapping or LEGACY_AUTOSPEND).items()):
        if cls not in classes:
            raise ValueError(f'legacy autospend class {cls!r} of {hero} is not among the classes XMen2.exe loads')
        rules = ';'.join(','.join(str(v) for v in (start, rate) + deltas) for start, rate, deltas in classes[cls])
        lines.append('\t'.join((hero, cls, rules)))
    return '\r\n'.join(lines) + '\r\n'


def parse_legacy(text):
    """{hero: (class, [(start, rate, deltas)])} from legacy_text's output; ValueError on anything else."""
    lines = [ln for ln in text.replace('\r\n', '\n').split('\n') if ln]
    if not lines or lines[0] != LEGACY_MAGIC:
        raise ValueError('not an autogrowth-legacy file')
    out = {}
    for ln in lines[1:]:
        hero, cls, rules = ln.split('\t')
        parsed = []
        for r in (rules.split(';') if rules else []):
            v = [int(x) for x in r.split(',')]
            if len(v) != 6:
                raise ValueError(f'{hero}: rule {r!r} has {len(v)} numbers')
            parsed.append((v[0], v[1], tuple(v[2:])))
        out[hero] = (cls, parsed)
    return out


def _herostat_roots(ctx):
    roots = []
    for ext in ('XMLB', 'engb'):
        try:
            roots.append(ctx.read_out_xmlb(f'Data/herostat.{ext}'))
        except KeyError:
            pass
    return roots


def run(ctx):
    """build step (after heroes): Data/autospend.XMLB = x1_bruiser / x1_support first, then the XML2 classes the
    built herostat still names; the rest dropped (XMen2.exe loads four)."""
    templates, _ = x1_templates(ctx.read_x1_xml('data/stat_rules.xml'))
    keep = used_classes(_herostat_roots(ctx)) - set(X1_TEMPLATES.values())
    try:
        done = ctx.patch_out_xmlb('Data/autospend', lambda root: set_x1_classes(root, templates, keep))
    except ValueError as e:
        ctx.error(f'autospend: {e}')
        return 0
    for rel in done:
        ctx.count('autospend_x1_classes')
        ctx.log(f'{rel}: x1_bruiser / x1_support first, XML2 classes kept: {sorted(keep)} (SPEC 94)')
    try:
        text = legacy_text(ctx.read_base_xmlb('Data/autospend.XMLB'))
    except ValueError as e:
        ctx.error(f'autospend: {e}')
        return len(done)
    ctx.write_bytes(LEGACY_REL, text.encode('latin-1'))
    ctx.set_count('autogrowth_legacy_heroes', len(LEGACY_AUTOSPEND))
    ctx.log(f'{LEGACY_REL}: the pre-SPEC 94 classes of {len(LEGACY_AUTOSPEND)} heroes (XML2 Fix re-bases older saves)')
    return len(done)
