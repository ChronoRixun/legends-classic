"""xml1build.autospend - XML1's automatic stat growth in Data/autospend.XMLB (SPEC 94).

The first game grants an automatic stat bonus on each level 2..40 from stat_rules.xml: every hero names a
template class (bruiser: Beast, Colossus, Rogue, Wolverine; support: the other eleven, ProfXAstral included)
and each listed level applies its bonus stats at once - one stat per level, two on levels 5, 10 .. 40
(default.xbe 0xaed70 / 0xaea90). Nothing is applied above level 40. In port units the totals are
body / mind / strength x4 (heroes.STAT_SCALE) and speed x2 (heroes.SPEED_MAP): bruiser body 80, strength 44,
mind 32, speed 16; support mind 112, strength 40, speed 16, body 4.

XMen2.exe grants no such table; on each level gained it walks the hero's Data/autospend.XMLB class
(0x43cf90 -> 0x43d000): the class record holds up to four 6-byte rules from +0x14 (start, rate, four signed
stat deltas; the parser at 0x43d0c0 stops at the count of 4, cmp [ebx+0x78],4) and a rule fires when
level >= start and (level - start) % rate == 0, adding its deltas once (reversed symmetrically on level loss).
The record cannot express a cap level, so past 40 the rules keep firing and the curve drifts from XML1's
flat line. The class attributes body / mind / speed / strength are the auto-spend weights of the unspent
points (normalized by the engine, 0x43d24d).

This module writes two classes, x1_bruiser / x1_support, whose periodic rules approximate the templates'
per-level tables (minimised per-level deviation; the fitted rules and their deviations are validated by
V-H17), keeps XML2's four classes for anything still referencing them, and heroes.py maps every XML1 hero
onto its XML1 template. XML1's `spend` lists (the suggested spend of the unspent point) become the classes'
auto-spend weights; XML1's `agility` suggestions map onto speed, the closest port stat.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

RULES_PER_CLASS = 4            # XMen2.exe 0x43d18d: cmp [ebx+0x78],4 - the parser drops every further <bonus>
AMOUNT_MAX = 127               # the four deltas are signed bytes (0x43d076 imul byte ptr)
LAST_X1_LEVEL = 40             # stat_rules.xml lists levels 2..40; nothing above

# XML1 stat_rules.xml bonus levels per template (levels 2..40; the entries with two bonuses are the
# multiples of 5), scaled to port units by cumulative() below: body / mind / strength x4, speed x2.
X1_BONUS_LEVELS = {
    'x1_bruiser': {'body': [2, 4, 6, 8, 9, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40],
                   'strength': [3, 7, 13, 17, 20, 23, 27, 30, 33, 37, 40],
                   'speed': [5, 10, 15, 19, 25, 29, 35, 39],
                   'mind': [5, 10, 11, 15, 21, 25, 31, 35]},
    'x1_support': {'mind': [2, 3, 4, 5, 8, 9, 10, 11, 12, 14, 15, 16, 18, 20, 21, 22, 24, 25, 26, 28, 30,
                            31, 32, 34, 35, 36, 38, 40],
                   'strength': [7, 13, 17, 20, 23, 27, 30, 33, 37, 40],
                   'speed': [5, 10, 15, 19, 25, 29, 35, 39],
                   'body': [6]},
}

# XML1 stat_rules.xml `spend` suggestions per template (47 entries each, one per unspent point; the
# `agility` suggestions are counted as speed). They become the class's auto-spend weights.
X1_SPEND_WEIGHTS = {
    'x1_bruiser': {'body': 19, 'strength': 12, 'speed': 11, 'mind': 5},
    'x1_support': {'mind': 13, 'speed': 14, 'body': 11, 'strength': 9},
}

# The fitted periodic rules (start, rate, {stat: amount}); chosen by least per-level deviation from the
# tables above under the four-rule limit. See SPEC 94 for the full per-level comparison and the past-40
# drift. Every stat's cumulative matches its XML1 total at 40 within 5 port points.
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
        (6, 35, {'body': 4}),
    ],
}

# Largest allowed per-level deviation from XML1's cumulative table (port points), per template and stat;
# the fit's documented worst error (V-H17 recomputes it from the rules).
X1_MAX_DEV = {
    'x1_bruiser': {'body': 4, 'strength': 4, 'speed': 2, 'mind': 4},
    'x1_support': {'mind': 6, 'strength': 4, 'speed': 2, 'body': 0},
}

STAT_SCALE = {'body': 4, 'mind': 4, 'strength': 4, 'speed': 2}
STATS = ('body', 'mind', 'speed', 'strength')


def cumulative(rules, level):
    """{stat: granted bonus points} the periodic rules give a hero reaching `level`, by the engine's rule
    (0x43d000): each rule whose start has passed adds its delta once per fire level <= level
    (a level fires when level >= start and (level - start) % rate == 0); between fires the granted
    bonus stays at its last value, and a level lost re-runs the same walk with the sign reversed."""
    out = {s: 0 for s in STATS}
    for start, rate, amounts in rules:
        if level < start:
            continue
        fires = (level - start) // rate + 1
        for stat, amount in amounts.items():
            out[stat] += amount * fires
    return out


def x1_cumulative(cls, level):
    """{stat: bonus} XML1's table grants at `level`, in port units (x4 body/mind/strength, x2 speed)."""
    out = {}
    for stat, levels in X1_BONUS_LEVELS[cls].items():
        out[stat] = STAT_SCALE[stat] * sum(1 for l in levels if l <= level)
    return out


def _class_element(cls):
    weights = X1_SPEND_WEIGHTS[cls]
    el = ET.Element('CharacterClass', {'name': cls,
                                       'body': str(weights['body']), 'mind': str(weights['mind']),
                                       'speed': str(weights['speed']), 'strength': str(weights['strength'])})
    for start, rate, amounts in X1_RULES[cls]:
        attrs = {'start': str(start), 'rate': str(rate)}
        for stat in STATS:
            if amounts.get(stat):
                attrs[stat] = str(amounts[stat])
        ET.SubElement(el, 'bonus', attrs)
    return el


def add_x1_classes(root):
    """Add (or refresh) the two XML1 template classes; True when the tree changed."""
    changed = False
    have = {c.get('name') for c in root.iter('CharacterClass')}
    for cls in X1_RULES:
        if cls not in have:
            root.append(_class_element(cls))
            changed = True
    return changed


def problems(root):
    """V-H17 for the built Data/autospend.XMLB: the two XML1 classes exist with the fitted rules, the rule
    count and byte range hold, and the simulated cumulative growth stays within the documented deviation of
    XML1's table at every level 2..40 (and matches the level-40 totals)."""
    out = []
    by_name = {c.get('name'): c for c in root.iter('CharacterClass')}
    for cls, rules in X1_RULES.items():
        el = by_name.get(cls)
        if el is None:
            out.append(f'{cls}: class missing from Data/autospend.XMLB')
            continue
        bonus = [b for b in el if b.tag.lower() == 'bonus']
        if len(bonus) > RULES_PER_CLASS:
            out.append(f'{cls}: {len(bonus)} bonus rules; XMen2.exe keeps {RULES_PER_CLASS} (0x43d18d)')
        fitted = [(int(start), int(rate), {s: int(a) for s, a in amounts.items()})
                  for start, rate, amounts in rules]
        actual = []
        for b in bonus:
            try:
                start, rate = int(b.get('start')), int(b.get('rate'))
                amounts = {s: int(b.get(s)) for s in STATS if b.get(s) is not None}
            except (TypeError, ValueError):
                out.append(f'{cls}: bonus rule {b.attrib} is not numeric')
                continue
            if start < 2 or rate < 1:
                out.append(f'{cls}: bonus rule {b.attrib} has start < 2 or rate < 1')
            if any(a > AMOUNT_MAX or a < -AMOUNT_MAX for a in amounts.values()):
                out.append(f'{cls}: bonus rule {b.attrib} amount outside signed byte')
            actual.append((start, rate, amounts))
        if actual != fitted:
            out.append(f'{cls}: bonus rules {actual} != the fitted {fitted}')
        for level in range(2, LAST_X1_LEVEL + 1):
            got = cumulative(actual, level)
            want = x1_cumulative(cls, level)
            for stat in STATS:
                dev = abs(got[stat] - want[stat])
                if dev > X1_MAX_DEV[cls][stat]:
                    out.append(f'{cls}: {stat} at level {level} deviates {dev} port points from XML1 '
                               f'(got {got[stat]}, want {want[stat]}, allowed {X1_MAX_DEV[cls][stat]})')
    return out


def run(ctx):
    """build step: Data/autospend.XMLB gains the two XML1 template classes (XML2's four are kept)."""
    done = ctx.patch_out_xmlb('Data/autospend', add_x1_classes)
    for rel in done:
        ctx.count('autospend_x1_classes')
        ctx.log(f'{rel}: added x1_bruiser / x1_support (XML1 stat_rules.xml templates, SPEC 94)')
    return len(done)
