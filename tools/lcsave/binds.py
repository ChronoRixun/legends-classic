"""The engine's numbering of a build's data (SPEC-new-save 3.2): for every save-bound domain, the key at each
position the old save stores, read from the build's own data files. This is what the player's build supplies at
run time (names never enter the repository); the era model (legacy.py) stores only key hashes.

Also the placed-entity ordinal model of a zone file (SPEC-old-save 1.13; verified against live ordinals of 7 zones
on two builds, 14 dumps, 0 mismatches - see CONVERTER-PORT.md section 4):
  an entity is numbered iff its vt+0x78 is false at zone load (0x486216);
  every class but the spawner answers with entity flag 17 = the smartent attribute, whose default is true for
  CPhysicalEntity and its subclasses (loader 0x498a10) and for CLightEntity (0x48377b) and false otherwise
  (0x460762); the spawner (0x48a4f0) stays smart iff monster_smartent and instantspawn and not checkteam
  (its own flag byte +0x27c bits 0, 1, 6; parser 0x48ab18-0x48ac01, every attribute default false).
"""
from __future__ import annotations

import glob
import hashlib
import os

import xmlb

from .keys import key_hash

# classname -> smartent default (RTTI hierarchy of XMen2.exe: the physical subclasses and the light entity)
SMART_DEFAULT_TRUE = frozenset({'physent', 'actor', 'affectableharment', 'doorent', 'guidedprojectileent',
                                'inventoryent', 'moverent', 'powertriggerent', 'projectileent', 'tornadoent',
                                'projectiletornadoent', 'rememberent', 'sentryent', 'tileent', 'lightent'})
SMART_DEFAULT_FALSE = frozenset({'ent', 'actionent', 'gameent', 'cameramagnetent', 'enabletargetent',
                                 'scripttriggerent', 'treasureent', 'waterent', 'zonelinkent', 'playerstartent',
                                 'waypointent', 'worldent'})
# costume slot of a herostat skin attribute (exe table 0x6d8aa0, lookup 0x4b9e8c; slot 0 = "skin")
COSTUME_SLOTS = {'': 0, 'astonishing': 1, 'aoa': 2, '60s': 3, '70s': 4, 'weaponx': 5, 'future': 6, 'winter': 7,
                 'civilian': 8}
COSTUME_SLOT_NAMES = {v: k for k, v in COSTUME_SLOTS.items()}
COSTUME_SLOT_COUNT = 10            # the mask is a u32, the cycling code uses 0..8, the unlock accepts 1..9
KEY_ITEM_NAMES = ('KEY1', 'KEY2', 'KEY3', 'KEYCARD1', 'KEYCARD2', 'KEYCARD3')     # old 1.4, six counters by name
TRIVIA_PER_ACT = 50                # old 1.8: bit = (act - 1) x 50 + (question - 1)
REVIEW_CATEGORIES = ('load', 'cin', 'comic', 'concept', 'stat')   # exe table 0x6d9414, loader 0x4ae3b0 (category =
                                                                  # index of the entry's type in this table)
REVIEW_PER_CATEGORY = 90           # 3 dwords per category, 90 bits used


class BindError(ValueError):
    pass


def _dec(path):
    return xmlb.decode(open(path, 'rb').read())


def _load(folder, name):
    for cand in (name + '.engb', name + '.xmlb', name + '.XMLB'):
        p = os.path.join(folder, cand)
        if os.path.isfile(p):
            return _dec(p), p
    raise BindError(f'{name}: no .engb / .xmlb under {folder}')


def _tb(e, k):
    return (e.get(k) or '').lower() == 'true'


def element_fingerprint(e):
    """SHA-256 of an element's canonical text (tag, sorted attributes, children in order) - the tag ledger's
    fingerprint (SPEC-new-save 3.3)"""
    return hashlib.sha256(_canon(e).encode('utf-8', 'replace')).hexdigest()


def _canon(e):
    parts = [e.tag, ';'.join(f'{k}={v}' for k, v in sorted(e.attrib.items()))]
    for c in e:
        parts.append('(' + _canon(c) + ')')
    return '|'.join(parts)


def numbered_entities(root):
    """-> ([(type, instance name, placement index)], problems) in ordinal order (ordinal = list index + 1).
    placement index = position among all placed instances in document order. A problem (unknown class, missing
    definition) means the zone's numbering cannot be modelled; the caller fails closed."""
    defs = {e.get('name'): e for e in root.iter('entity')}
    out, problems, k = [], [], 0
    for ei in root.iter('entinst'):
        t = ei.get('type')
        d = defs.get(t)
        insts = [i.get('name') for i in ei.iter('inst')]
        if d is None:
            problems.append(f'no entity definition for type {t!r}')
            k += len(insts)
            continue
        cls = (d.get('classname') or '').lower()
        sm = (d.get('smartent') or '').lower()
        if cls == 'monsterspawnerent':
            stays_smart = _tb(d, 'monster_smartent') and _tb(d, 'instantspawn') and not _tb(d, 'checkteam')
        elif cls in SMART_DEFAULT_TRUE:
            stays_smart = sm != 'false'
        elif cls in SMART_DEFAULT_FALSE:
            stays_smart = sm == 'true'
        else:
            problems.append(f'unknown entity class {cls!r} (type {t!r})')
            stays_smart = True
        for n in insts:
            if not stays_smart:
                out.append((t, n, k))
            k += 1
    return out, problems


class Binds:
    """position -> key (and key hash) per domain for one build. Attributes are plain lists / dicts:

    stat[i]            stats name at stats-table index i (index 0 = None, reserved)
    hero_count         herostat entries (hero blocks of a save)
    costume[hero]      {slot: skin attribute name}
    shared_talent[i]   shared talent name at position i (talent ids 0..99)
    hero_talent[hero]  talent names of the hero's talent file by position (ids (stats index + 1) x 100 + position)
    item[i]            item definition name; item_class[i], item_type[i]
    enhancement[r]     key fields of record number r (prefix / suffix / tr_item enhancement / item's own)
    item_own[i]        record numbers of definition i's own enhancements; trit_own[t] the same per special item
    prefix_range, suffix_range, trit_range   (lo, hi) record number ranges
    name_a[i], name_b[class][i], trit[i]     the three item name tables (trit[i] = its persistent tag)
    mission_file[i], objective[i] = (file, name or tag)
    course[i], grade[i], review[(category, i)] = (type, name), xpoint[i] = (zone, name)
    trivia[(act, i)] = tag; zone_names = set of zone paths the data knows
    zones[zone] = dict(path, sha1, numbered, problems, placed)   (lazy: zone_numbering(zone))
    """

    def __init__(self, build):
        self.build = build
        from .zonecompat import load
        self.zone_prefixes = load(build)
        D = os.path.join(build, 'Data')
        hs, _ = _load(D, 'herostat')
        ns, _ = _load(D, 'npcstat')
        heroes = [e.get('name') for e in hs if e.tag == 'stats']
        npcs = [e.get('name') for e in ns if e.tag == 'stats']
        if any(n is None for n in heroes + npcs):
            raise BindError('a stats entry has no name')
        self.stat = [None] + heroes + npcs
        self.hero_count = len(heroes)
        self.costume = {}
        self.hero_talent = {}
        for e in hs:
            if e.tag != 'stats':
                continue
            slots = {}
            for a in e.attrib:
                if a == 'skin':
                    slots[0] = 'skin'
                elif a.startswith('skin_') and a[5:].lower() in COSTUME_SLOTS:
                    slots[COSTUME_SLOTS[a[5:].lower()]] = a
            self.costume[e.get('name')] = slots
            try:
                r, _ = _load(os.path.join(D, 'talents'), e.get('name').lower())
                self.hero_talent[e.get('name')] = [t.get('name') for t in r if t.tag == 'talent']
            except BindError:
                self.hero_talent[e.get('name')] = []
        sh, _ = _load(D, 'shared_talents')
        self.shared_talent = [e.get('name') for e in sh if e.tag == 'talent']
        inv, _ = _load(D, 'items')
        items = [e for e in inv if e.tag == 'item']
        self.item = [e.get('name') for e in items]
        self.item_class = [(e.get('class') or '').lower() for e in items]
        self.item_type = [(e.get('type') or '').lower() for e in items]
        self.enhancement = []
        for sec, letter in (('prefixes', 'p'), ('suffixes', 's')):
            s = inv.find(sec)
            lo = len(self.enhancement)
            for e in (s if s is not None else []):
                self.enhancement.append((letter, e.get('groupname') or '', e.get('enemy_level') or ''))
            setattr(self, ('prefix' if letter == 'p' else 'suffix') + '_range', (lo, len(self.enhancement)))
        trs = [e for e in inv if e.tag == 'tr_item']
        self.trit, self.trit_own, self.trit_fingerprint, self.trit_item = [], [], [], []
        lo = len(self.enhancement)
        for i, e in enumerate(trs):
            tag = f't{i + 1}'                       # first-population tag (the tag ledger pins it to the fingerprint)
            self.trit.append(tag)
            self.trit_fingerprint.append(element_fingerprint(e))
            req = e.find('require')
            self.trit_item.append(req.get('item') if req is not None else None)
            own = []
            for j, x in enumerate(e.findall('enhancement')):
                own.append(len(self.enhancement))
                self.enhancement.append(('t', tag, f'e{j + 1}'))
            self.trit_own.append(own)
        self.trit_range = (lo, len(self.enhancement))
        self.item_own = []
        self.item_own_fingerprints = []
        for e in items:
            own, fps = [], []
            for j, x in enumerate(e.findall('enhancement')):
                own.append(len(self.enhancement))
                self.enhancement.append(('i', e.get('name'), f'e{j + 1}'))
                fps.append(element_fingerprint(x))
            self.item_own.append(own)
            self.item_own_fingerprints.append(fps)
        nm = inv.find('ItemNames')
        self.name_a = [e.get('name') for e in nm] if nm is not None else []
        cn = inv.find('ClassNames')
        self.name_b = {}
        for e in (cn if cn is not None else []):
            self.name_b.setdefault((e.get('class') or '').lower(), []).append(e.get('name'))
        ms, _ = _load(os.path.join(D, 'missions'), 'missions')
        self.mission_file = []
        for e in ms.iter():
            if e is ms or not e.attrib:
                continue
            f = next(iter(e.attrib.values()), '')
            base = os.path.basename(f.replace('\\', '/'))
            if base.lower().endswith('.xmlb'):
                base = base[:-5]
            self.mission_file.append(base.lower())
        self.objective = []
        for f in self.mission_file:
            r, _ = _load(os.path.join(D, 'missions'), f)
            unnamed = 0
            for e in r.iter():
                if e.tag.lower() == 'objective':
                    n = e.get('name')
                    if not n:
                        unnamed += 1
                        n = f'o{unnamed}'           # persistent tag for an unnamed objective (two exist)
                    self.objective.append((f, n))
        dr, _ = _load(D, 'dangerroom')
        grades = [g for g in dr if g.tag == 'GRADE']
        self.grade = [g.get('name') or '' for g in grades]
        self.course = [c.get('name') or '' for g in grades for c in g if c.tag == 'COURSE']
        self.course_grade = [gi for gi, g in enumerate(grades) for c in g if c.tag == 'COURSE']
        self.arenas = {(e.get('zone') or '').lower() for e in dr if e.tag == 'ARENA'}
        rv, _ = _load(D, 'review_paths')
        self.review = {}
        per = {}
        for e in rv:
            t = (e.get('type') or '').lower()
            per.setdefault(t, []).append((t, e.get('name') or ''))
        self.review_types = list(REVIEW_CATEGORIES)
        for c, t in enumerate(REVIEW_CATEGORIES):
            for i, k in enumerate(per.get(t, [])):
                self.review[(c, i)] = k
        xp, _ = _load(D, 'xtraction_points')
        self.xpoint = [(e.get('zone') or '', e.get('name') or '') for e in xp]
        tv, _ = _load(D, 'trivia')
        mode = tv.get('persistence') or 'legacy'
        if mode not in ('legacy', 'compact'):
            raise ValueError('unsupported trivia persistence mode')
        self.trivia_compact = mode == 'compact'
        self.trivia = {}
        per = {}
        for e in tv:
            act = int(e.get('act') or 0)
            per.setdefault(act, []).append(e)
        for act, lst in per.items():
            for i, e in enumerate(lst):
                self.trivia[(act, i)] = (f'q{i + 1}', element_fingerprint(e))
        if any(not 1 <= a <= 0x7fffffff or i >= TRIVIA_PER_ACT for a, i in self.trivia):
            raise ValueError('invalid trivia act/question position')
        if self.trivia_compact and len(self.trivia) > 250:
            raise ValueError('native trivia budget exceeded (250)')
        self.trivia_bits = {k: (n if self.trivia_compact else (k[0] - 1) * TRIVIA_PER_ACT + k[1])
                            for n, k in enumerate(sorted(self.trivia))}
        zi, _ = _load(D, 'zoneinfo')
        self.zone_names = {(e.get('name') or '').lower() for e in zi if e.tag == 'zone'}
        self._zones = {}

    # ---- keys per domain (canonical fields; keys.key_hash(*fields) is the stored form)
    def key_stat(self, index):
        n = self.stat[index] if 0 < index < len(self.stat) else None
        return (n,) if n else None

    def key_item(self, index):
        return (self.item[index],) if 0 <= index < len(self.item) else None

    def key_enh(self, record):
        return self.enhancement[record] if 0 <= record < len(self.enhancement) else None

    def key_name_a(self, index):
        return (self.name_a[index],) if 0 <= index < len(self.name_a) else None

    def key_name_b(self, cls, index):
        lst = self.name_b.get(cls, [])
        return (cls, lst[index]) if 0 <= index < len(lst) else None

    def key_trit(self, index):
        return (self.trit[index],) if 0 <= index < len(self.trit) else None

    def key_talent(self, talent_id, hero_block=None):
        """old talent id -> key fields. ids below 100 are shared; others are (stats index + 1) x 100 + position"""
        if talent_id < 100:
            return ('shared', self.shared_talent[talent_id]) if talent_id < len(self.shared_talent) else None
        stats_index = talent_id // 100 - 1
        pos = talent_id % 100
        name = self.stat[stats_index] if 0 < stats_index < len(self.stat) else None
        lst = self.hero_talent.get(name or '', [])
        return (name, lst[pos]) if name and pos < len(lst) else None

    def key_costume(self, hero_name, slot):
        return (hero_name, 'skin' if slot == 0 else 'skin_' + COSTUME_SLOT_NAMES[slot]) if 0 <= slot < 9 else None

    def key_objective(self, index):
        return self.objective[index] if 0 <= index < len(self.objective) else None

    def key_course(self, index):
        return (self.course[index],) if 0 <= index < len(self.course) else None

    def key_grade(self, index):
        return (self.grade[index],) if 0 <= index < len(self.grade) else None

    def key_review(self, category, index):
        return self.review.get((category, index))

    def key_xpoint(self, index):
        return self.xpoint[index] if 0 <= index < len(self.xpoint) else None

    def key_trivia(self, act, index):
        t = self.trivia.get((act, index))
        return (str(act), t[0]) if t else None

    def key_zone(self, name):
        return (name,) if name else None

    # ---- zones
    def zone_file(self, zone):
        base = os.path.join(self.build, 'Maps', *zone.replace('\\', '/').split('/'))
        for ext in ('.engb', '.xmlb', '.XMLB'):
            if os.path.isfile(base + ext):
                return base + ext
        return None

    def zone_numbering(self, zone):
        """-> dict(sha1, numbered [(type, name, placement index)], problems) or None when the build has no file"""
        z = zone.lower()
        if z in self._zones:
            return self._zones[z]
        p = self.zone_file(z)
        if p is None:
            self._zones[z] = None
            return None
        raw = open(p, 'rb').read()
        num, problems = numbered_entities(xmlb.decode(raw))
        self._zones[z] = dict(path=p, sha1=hashlib.sha1(raw).hexdigest(), numbered=num, problems=problems)
        return self._zones[z]

    def all_zone_files(self):
        out = []
        for p in sorted(glob.glob(os.path.join(self.build, 'Maps', '**', '*.engb'), recursive=True)):
            out.append(os.path.relpath(p, os.path.join(self.build, 'Maps')).replace('\\', '/')[:-5].lower())
        return out

    # ---- the complete hash tables (what the era model stores)
    def hash_tables(self, *, include_conversation_digest=True):
        """{domain: [key hash by position]} for the list-shaped domains, plus the structured ones"""
        T = {}
        T['STAT'] = [key_hash(*self.key_stat(i)) if self.key_stat(i) else None for i in range(len(self.stat))]
        T['ITEM'] = [key_hash(n) for n in self.item]
        T['ITEM_class'] = list(self.item_class)
        T['ENHC'] = [key_hash(*k) for k in self.enhancement]
        T['NAMA'] = [key_hash(n) for n in self.name_a]
        T['NAMB'] = {c: [key_hash(c, n) for n in lst] for c, lst in self.name_b.items()}
        T['TRIT'] = [key_hash(t) for t in self.trit]
        T['TALN_shared'] = [key_hash('shared', n) for n in self.shared_talent]
        T['TALN_hero'] = {key_hash(h): [key_hash(h, t) for t in lst] for h, lst in self.hero_talent.items()}
        T['COST'] = {key_hash(h): {str(s): key_hash(*self.key_costume(h, s)) for s in range(9)} for h in self.costume}
        T['MSNF'] = [key_hash(f) for f in self.mission_file]
        T['OBJV'] = [key_hash(*k) for k in self.objective]
        T['DRCS'] = [key_hash(n) for n in self.course]
        T['DRGR'] = [key_hash(n) for n in self.grade]
        T['REVW'] = {f'{c},{i}': key_hash(*k) for (c, i), k in self.review.items()}
        T['XPNT'] = [key_hash(*k) for k in self.xpoint]
        T['TRIV'] = {f'{a},{i}': key_hash(str(a), t[0]) for (a, i), t in self.trivia.items()}
        T['ZONE'] = sorted(key_hash(z) for z in self.zone_names)
        T['hero_count'] = self.hero_count
        T['ITEM_own'] = [list(x) for x in self.item_own]
        T['TRIT_own'] = [list(x) for x in self.trit_own]
        T['ENHC_ranges'] = dict(prefix=list(self.prefix_range), suffix=list(self.suffix_range), trit=list(self.trit_range))
        T['conversation_digest'] = self.conversation_digest() if include_conversation_digest else '00' * 32
        return T

    def conversation_digest(self):
        """SHA-256 over the sorted (relative path lower-cased, SHA-1) of every file under Conversations
        (SPEC-new-save 2.12: the conversation bits of a zone record are valid only for unchanged conversation
        content)"""
        root = os.path.join(self.build, 'Conversations')
        h = hashlib.sha256()
        paths = sorted((os.path.relpath(p, root).replace(os.sep, '/').lower(), p)
                       for p in glob.glob(os.path.join(root, '**', '*'), recursive=True) if os.path.isfile(p))
        previous = None
        for rel, p in paths:
            if rel == previous:
                raise ValueError('duplicate conversation path after case normalization')
            previous = rel
            with open(p, 'rb') as f:
                h.update(rel.encode('utf-8') + b'\0' + hashlib.sha1(f.read()).digest())
        return h.hexdigest()
