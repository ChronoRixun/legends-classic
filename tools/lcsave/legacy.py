"""The era model (SPEC-new-save 5.3 / revision 2.2 section 15): what every builder release numbered how, and the
rule that tells an old save's era from its contents.

data/legacy_eras.json (hashes only, written by `python -m lcsave eras` from real builds; never edited by hand):

  reference      the build every era is expressed against (the last old version, 0.1.10 / content version 13):
                 the full hash tables of binds.Binds.hash_tables()
  eras[cv]       one entry per builder release content version (5 = 0.1.3 .. 13 = 0.1.10): per domain either
                 "same" (equal to the reference) or the era's own table; zone deltas for the zones whose numbered
                 entity list differs from the reference: {zone hash: {"map": [reference ordinal or 0 per era ordinal],
                 "ambiguous": [era ordinals that twins make undecidable]}}; "hero_shared_holdable": {hero hash: [shared positions the hero's herostat lists]}

Era detection (the rule, applied per save; the result and its evidence are recorded in LGCY and the report):
  1. talents - the "start era": the newest era in which every shared talent id held by every hero maps to a
     talent that hero's herostat lists (the most ranks kept); ties (identical mappings) go to the newest era;
  2. zones - per record: the newest era whose numbered-entity list has, at every ordinal the record uses, the
     definition and instance names the record itself stores (old 1.13: the two name handles); a record no era
     explains is dropped with that reason;
  3. items - the "writer era" (the era that wrote the file): the era of the current zone's record when that zone
     distinguishes eras, else the start era; definition indices and enhancement records are read with that era's
     tables and cross-checked (every own record belongs to the instance's definition or special item).
"""
from __future__ import annotations

import json
import os

from .keys import key_hash

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
ERAS_FILE = os.path.join(DATA_DIR, 'legacy_eras.json')
# builder release -> content version (git tags v0.1.3 .. v0.1.10, tools/xml1builder/__init__.py)
RELEASES = {'0.1.3': 5, '0.1.4': 6, '0.1.5': 7, '0.1.6': 8, '0.1.7': 9, '0.1.8': 11, '0.1.9': 12, '0.1.10': 13}
CONTENT_TO_RELEASE = {v: k for k, v in RELEASES.items()}
LIST_DOMAINS = ('STAT', 'ITEM', 'ITEM_class', 'ENHC', 'NAMA', 'TRIT', 'TALN_shared', 'MSNF', 'OBJV', 'DRCS', 'DRGR',
                'XPNT', 'ZONE')
DICT_DOMAINS = ('NAMB', 'TALN_hero', 'COST', 'REVW', 'TRIV')


class EraError(ValueError):
    pass


def load_eras(path=ERAS_FILE):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


class Era:
    """the resolved tables of one era (reference tables with the era's differences applied)"""

    def __init__(self, model, cv):
        self.cv = int(cv)
        self.release = CONTENT_TO_RELEASE.get(self.cv, str(cv))
        ref = model['reference']
        e = model['eras'][str(cv)]
        self.tables = {}
        for d in LIST_DOMAINS + DICT_DOMAINS + ('ITEM_own', 'TRIT_own', 'ENHC_ranges'):
            v = e.get(d, 'same')
            self.tables[d] = ref[d] if v == 'same' else v
        self.conversation_digest = e.get('conversation_digest')
        self.hero_count = e.get('hero_count', ref['hero_count'])
        self.zone_deltas = e.get('zones', {})
        self.hero_shared_holdable = e.get('hero_shared_holdable', {})

    def table(self, domain):
        return self.tables[domain]

    def zone_map(self, zone_hash):
        """-> (map: era ordinal k -> map[k - 1] = reference ordinal or 0, ambiguous era ordinals) or None when
        the era numbers the zone exactly as the reference does"""
        d = self.zone_deltas.get(zone_hash)
        return (d['map'], d.get('ambiguous', [])) if d else None


def eras_of(model):
    """every Era of the model, newest first"""
    return [Era(model, cv) for cv in sorted((int(k) for k in model['eras']), reverse=True)]


# ------------------------------------------------------------------------------------------------ detection
def shared_ids_by_hero(old):
    """{stats index: {shared talent ids}} over the hero blocks and the restore records"""
    out = {}
    for n, h in enumerate(old['heroes']):
        out[n + 1] = {e['id'] for e in h['attributes']['talents'][:h['attributes']['count']] if e['id'] < 100}
    for n, r in enumerate(old['restore']):
        ids = {e['id'] for e in r['attributes']['talents'][:r['attributes']['count']] if e['id'] < 100}
        if ids:
            out.setdefault(n, set()).update(ids)     # restore record n = stats-table position n (unknowns U6)
    return out


def talent_era(old, eras, ref_stat_hashes):
    """-> (Era, evidence dict). The newest era in which every held shared id is a talent the hero's herostat
    lists; otherwise the era keeping the most such ranks."""
    held = shared_ids_by_hero(old)
    best = None
    scores = {}
    for era in eras:                         # newest first
        table = era.table('TALN_shared')
        good = total = 0
        unexplained = []
        for stats_index, ids in held.items():
            hero_hash = ref_stat_hashes[stats_index] if stats_index < len(ref_stat_hashes) else None
            holdable = set(era.hero_shared_holdable.get(hero_hash or '', []))
            for tid in ids:
                total += 1
                if tid < len(table) and tid in holdable:
                    good += 1
                else:
                    unexplained.append((stats_index, tid))
        scores[era.cv] = (good, total, unexplained)
        if best is None or good > scores[best.cv][0]:
            best = era
    good, total, unexplained = scores[best.cv]
    return best, dict(held=sum(len(v) for v in held.values()), explained=good,
                      unexplained=[list(x) for x in unexplained], scores={cv: s[0] for cv, s in scores.items()})


def zone_record_eras(names_by_ordinal, zone_hash, eras, ref_numbered_hashes):
    """which eras explain a zone record: names_by_ordinal = {ordinal: (def name hash, inst name hash)} of the
    record's numbered states; ref_numbered_hashes = [(type hash, name hash)] of the reference build in ordinal
    order. -> [Era] newest first (an era whose list matches every used ordinal), each with its ordinal map."""
    out = []
    for era in eras:
        delta = era.zone_map(zone_hash)
        ok = True
        for k, (dh, ih) in names_by_ordinal.items():
            if delta is None:
                ref_k = k
            else:
                m, _ = delta
                ref_k = m[k - 1] if 1 <= k <= len(m) else 0
            if ref_k == 0 or ref_k > len(ref_numbered_hashes) or ref_numbered_hashes[ref_k - 1] != (dh, ih):
                ok = False
                break
        if ok:
            out.append(era)
    return out


# ------------------------------------------------------------------------------------------------ generation
def build_era_entry(binds, ref_tables, ref_binds):
    """one era's JSON entry from its Binds, expressed against the reference tables (developer command)"""
    T = binds.hash_tables()
    e = {}
    for d in LIST_DOMAINS + DICT_DOMAINS + ('ITEM_own', 'TRIT_own', 'ENHC_ranges'):
        e[d] = 'same' if T[d] == ref_tables[d] else T[d]
    e['hero_count'] = T['hero_count']
    e['conversation_digest'] = T['conversation_digest']
    # shared talents each hero's herostat lists (the talent names a hero can hold), by era position
    import xmlb  # noqa: E402 (tools/ on sys.path)
    hs = xmlb.decode(open(os.path.join(binds.build, 'Data', 'herostat.engb'), 'rb').read())
    pos = {n.lower(): i for i, n in enumerate(binds.shared_talent)}
    hold = {}
    for s in hs:
        if s.tag != 'stats':
            continue
        lst = sorted({pos[(t.get('name') or '').lower()] for t in s if t.tag == 'talent' and (t.get('name') or '').lower() in pos})
        hold[key_hash(s.get('name'))] = lst
    e['hero_shared_holdable'] = hold
    # zone deltas against the reference numbering
    zones = {}
    for z in ref_binds.all_zone_files():
        rz = ref_binds.zone_numbering(z)
        ez = binds.zone_numbering(z)
        if rz is None or ez is None or rz['problems'] or ez['problems']:
            continue
        a = [(t, n) for t, n, _ in ez['numbered']]
        b = [(t, n) for t, n, _ in rz['numbered']]
        if a == b:
            continue
        m, ambiguous = align(a, b)
        zones[key_hash(z)] = dict(map=m, ambiguous=ambiguous)
    e['zones'] = zones
    return e


def align(a, b):
    """map every element of a (era) to a position in b (reference): a longest-common-subsequence alignment,
    computed forwards and backwards. -> ([1-based reference ordinal per era ordinal, 0 = no match], [era ordinals
    the two alignments disagree on or leave unmatched - twins the names cannot tell apart; the converter drops
    those states])"""
    import difflib

    def lcs_map(x, y):
        m = [0] * len(x)
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=x, b=y, autojunk=False).get_opcodes():
            if op == 'equal':
                for k in range(i2 - i1):
                    m[i1 + k] = j1 + k + 1
        return m

    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    left = lcs_map(a, b)
    rev = lcs_map(a[::-1], b[::-1])
    right = [0 if v == 0 else len(b) - v + 1 for v in rev[::-1]]
    # an entity whose names are unique on both sides is matched by name whatever the LCS did (a moved entity:
    # 0.1.8 numbered its fall volumes in place, 0.1.10 appends them)
    where = {y: j + 1 for j, y in enumerate(b) if cb[y] == 1}
    for i, x in enumerate(a):
        if ca[x] == 1 and x in where:
            left[i] = right[i] = where[x]
    ambiguous = [i + 1 for i in range(len(a))
                 if left[i] != right[i] or not left[i] or (ca[a[i]] > 1 and ca[a[i]] != cb[a[i]])]
    return left, ambiguous
