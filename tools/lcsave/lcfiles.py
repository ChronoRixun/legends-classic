"""The save-format data files of a build (SPEC-new-save 3.4 / 5.3; legends-classic SPEC 70): the binary files
XML2 Fix reads at start-up, written by the build from its own data.

  Data/lcsave/catalogue.lcc   the master catalogue with plain keys (3.4 a)
  Data/lcsave/legacy.lcm      the era model for the one-time converter (5.3; the binary conventions of 3.4)
  < beside each save-bound data file >.lcbind   position -> (id, key) per domain of that file (3.4 b)

Binary conventions (little-endian throughout; where SPEC-new-save 3.4 leaves a byte open, SPEC 70 of the builder
records the choice made here):

  str            u16 byte count + that many bytes (canonical key bytes, keys.canonical_key; empty = count 0)
  CRC-32         zlib (IEEE 802.3), of everything after the CRC field
  domain order   ascending domain number (keys.DOMAINS); catalogue entries ascending id; bind lists ascending
                 domain number too
  packed         no alignment padding anywhere

Bind-row group / position per domain (the engine's numbering, SPEC-new-save 3.2):
  STAT  group 0, position = stats-table index (herostat from 1, npcstat continuing)
  COST  group = hero's stats-table index, position = costume slot 0..8
  TALN  group 0 = shared talents (position = shared index); group = hero's stats-table index (position = talent
        file index). Old talent id = position when group 0, else (group + 1) * 100 + position... group is the
        stats-table index, so the id is (group + 1) * 100 + position for a hero talent.
  ITEM  group = NAMB category of the item's class (1 belt, 2 gloves, 3 armor, 0 none), position = definition index
  ENHC  group 0, position = record number
  NAMA  group 0, position
  NAMB  group = category (1 belt, 2 gloves, 3 armor), position within the category
  TRIT  group 0, position
  MSNF  group 0, position = mission file index
  OBJV  group = mission file index, position = global objective index
  DRCS  group = grade index, position = global course position
  DRGR  group 0, position = grade index
  REVW  group = category index (0 load, 1 cin, 2 comic, 3 concept, 4 stat), position within the category
  XPNT  group 0, position
  TRIV  group = act, position = question index within the act (engine bit = (act - 1) * 50 + position)
  ZONE  no bind list (saves name zones by string); the legacy map names zones by catalogue id

Bind rule: 1 for every list of this release (the first numbered version of the SPEC 3.2 rules).
"""
from __future__ import annotations

import glob
import hashlib
import os
import struct

from . import binds as bindsmod
from . import catalogue as catmod
from . import legacy as legacymod
from .keys import DOMAINS, DOMAIN_NUMBER, canonical_key, key_hash, make_id, crc32

LCC_MAGIC = b'LCCAT2\0\0'
LCM_MAGIC = b'LCLGM1\0\0'
LCB_MAGIC = b'LCBIND1\0'
BIND_RULE = 1
# catalogue.lcc carries plain keys generated from the writing build's own data (decision D3): an entry whose key
# the build does not know (content of an earlier era) gets an empty key and resolves by id only
NAMB_CATEGORIES = {'belt': 1, 'gloves': 2, 'armor': 3}
LC_DIR = ('Data', 'lcsave')                      # where catalogue.lcc and legacy.lcm go inside a build
CATALOGUE_LCC = os.path.join(*LC_DIR, 'catalogue.lcc')
LEGACY_LCM = os.path.join(*LC_DIR, 'legacy.lcm')


class LCFileError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ low level
def _u8(n):
    return struct.pack('<B', n)


def _u16(n):
    return struct.pack('<H', n)


def _u32(n):
    return struct.pack('<I', n)


def _str(b):
    b = bytes(b)
    if len(b) > 0xFFFF:
        raise LCFileError(f'str of {len(b)} bytes does not fit u16')
    return _u16(len(b)) + b


class _Reader:
    def __init__(self, buf, what):
        self.buf = buf
        self.off = 0
        self.what = what

    def take(self, n):
        if self.off + n > len(self.buf):
            raise LCFileError(f'{self.what}: truncated at {self.off:#x} (want {n} of {len(self.buf)})')
        b = self.buf[self.off:self.off + n]
        self.off += n
        return b

    def u8(self):
        return struct.unpack('<B', self.take(1))[0]

    def u16(self):
        return struct.unpack('<H', self.take(2))[0]

    def u32(self):
        return struct.unpack('<I', self.take(4))[0]

    def s(self):
        return self.take(self.u16())

    def done(self):
        if self.off != len(self.buf):
            raise LCFileError(f'{self.what}: {len(self.buf) - self.off} trailing bytes')


def _header_check(r, magic, *vals):
    """magic, the caller's header u32s, file length, crc; returns (vals, body reader) after the CRC check."""
    if r.take(8) != magic:
        raise LCFileError(f'{r.what}: bad magic')
    got = [r.u32() for _ in vals]
    length, crc = r.u32(), r.u32()
    if length != len(r.buf):
        raise LCFileError(f'{r.what}: header length {length} != file size {len(r.buf)}')
    if crc32(r.buf[r.off:]) != crc:
        raise LCFileError(f'{r.what}: CRC mismatch')
    return got


def _with_header(magic, vals, body):
    head = magic + b''.join(_u32(v) for v in vals)
    return head + _u32(len(head) + 8 + len(body)) + _u32(crc32(body)) + body


# ------------------------------------------------------------------------------------------------ catalogue.lcc
def write_catalogue_lcc(cat, key_texts, content_version):
    """cat: catalogue.Catalogue; key_texts: {tag: {hash: canonical key bytes}} of the writing build (an entry
    whose hash the build does not know gets an empty key). content_version: the build's."""
    body = b''
    domains = sorted(cat.data['domains'].items(), key=lambda kv: DOMAIN_NUMBER[kv[0]])
    for tag, dom in domains:
        entries = sorted(dom['entries'], key=lambda e: e['serial'])
        d = tag.encode('ascii') + _u8(DOMAIN_NUMBER[tag]) + b'\0\0\0' + _u32(len(entries))
        for e in entries:
            key = key_texts.get(tag, {}).get(e['hash'], b'')
            aliases = [key_texts.get(tag, {}).get(a) for a in e.get('aliases', [])]
            aliases = [a for a in aliases if a]
            d += (_u32(make_id(DOMAIN_NUMBER[tag], e['serial'])) + _u32(e.get('attributes', 0))
                  + _u16(1 if e.get('retired') else 0) + _u32(e.get('successor', 0))
                  + _str(key) + _u16(len(aliases)) + b''.join(_str(a) for a in aliases))
        body += d
    return _with_header(LCC_MAGIC, (cat.revision, content_version, len(domains)), body)


def read_catalogue_lcc(buf):
    r = _Reader(buf, 'catalogue.lcc')
    revision, content_version, domain_count = _header_check(r, LCC_MAGIC, 0, 0, 0)
    domains = {}
    for _ in range(domain_count):
        tag = r.take(4).decode('ascii')
        number, zero, count = r.u8(), r.take(3), r.u32()
        if zero != b'\0\0\0' or DOMAINS.get(number) != tag:
            raise LCFileError(f'catalogue.lcc: bad domain header {tag!r} {number}')
        entries = []
        for _ in range(count):
            e = {'id': r.u32(), 'attributes': r.u32(), 'flags': r.u16(), 'successor': r.u32(), 'key': r.s()}
            e['aliases'] = [r.s() for _ in range(r.u16())]
            entries.append(e)
        if [e['id'] for e in entries] != sorted(e['id'] for e in entries):
            raise LCFileError(f'catalogue.lcc: {tag} entries not ascending')
        domains[tag] = entries
    r.done()
    return {'revision': revision, 'content_version': content_version, 'domains': domains}


# ------------------------------------------------------------------------------------------------ .lcbind
def write_lcbind(data_sha1, lists):
    """data_sha1: 20 bytes of the data file the bind describes; lists: [(domain tag, [(group, position, id,
    key bytes)])] - written in ascending domain-number order, bind rule BIND_RULE."""
    body = bytes(data_sha1)
    for tag, rows in sorted(lists, key=lambda kv: DOMAIN_NUMBER[kv[0]]):
        body += tag.encode('ascii') + _u32(BIND_RULE) + _u32(len(rows))
        for group, position, ident, key in rows:
            body += _u32(group) + _u32(position) + _u32(ident) + _str(key)
    return _with_header(LCB_MAGIC, (), body)


def read_lcbind(buf):
    r = _Reader(buf, 'lcbind')
    _header_check(r, LCB_MAGIC)
    sha1 = r.take(20)
    lists = []
    while r.off < len(buf):
        tag = r.take(4).decode('ascii')
        if tag not in DOMAIN_NUMBER:
            raise LCFileError(f'lcbind: unknown domain tag {tag!r}')
        rule, count = r.u32(), r.u32()
        rows = [(r.u32(), r.u32(), r.u32(), r.s()) for _ in range(count)]
        lists.append((tag, rule, rows))
    return {'sha1': sha1, 'lists': lists}


# ------------------------------------------------------------------------------------------------ legacy.lcm
# pseudo tables of legacy.lcm (not catalogue domains): the own-record sets of SPEC 5.3's checks
# (group = definition / trit index, position = k, id = the enhancement record's catalogue id)
LCM_PSEUDO = ('IOWN', 'TOWN')


def _lcm_tables_with_ids(tables, cat, ref_stat):
    """the (tag, rows) tables of one era's resolved hash tables (legacy.Era.tables), every hash replaced by its
    catalogue id; a hash the catalogue does not know is an error (the catalogue is populated from every release
    build first)."""
    made = {}

    def id_of(tag):
        if tag not in made:
            def f(h, _tag=tag):
                v = cat.lookup(_tag, h) if h else None
                if v is None and h:
                    raise LCFileError(f'legacy.lcm: {_tag} hash {h[:16]}... is not in the catalogue')
                return v or 0
            made[tag] = f
        return made[tag]

    stat_by_hash = {h: i for i, h in enumerate(ref_stat) if h}

    def stat_index_of(hero_hash):
        if hero_hash not in stat_by_hash:
            raise LCFileError(f'legacy.lcm: hero hash {hero_hash[:16]}... not in the reference STAT table')
        return stat_by_hash[hero_hash]

    def rows(tag, entries):
        return [(0, i, id_of(tag)(h) if h else 0) for i, h in enumerate(entries)]

    T = tables
    out = [('STAT', rows('STAT', T['STAT']))]
    out.append(('ITEM', [(NAMB_CATEGORIES.get((T['ITEM_class'][i] or '').lower(), 0), i, id_of('ITEM')(h))
                         for i, h in enumerate(T['ITEM'])]))
    out.append(('ENHC', rows('ENHC', T['ENHC'])))
    out.append(('NAMA', rows('NAMA', T['NAMA'])))
    namb = []
    for cls, lst in sorted(T['NAMB'].items()):
        c = NAMB_CATEGORIES.get(cls.lower())
        if c is None:
            raise LCFileError(f'legacy.lcm: NAMB category {cls!r} is not belt / gloves / armor')
        namb += [(c, i, id_of('NAMB')(h)) for i, h in enumerate(lst)]
    out.append(('NAMB', namb))
    out.append(('TRIT', rows('TRIT', T['TRIT'])))
    taln = rows('TALN', T['TALN_shared'])
    for hh, lst in sorted(T['TALN_hero'].items()):
        taln += [(stat_index_of(hh), i, id_of('TALN')(h)) for i, h in enumerate(lst)]
    out.append(('TALN', taln))
    cost = []
    for hh, slots in sorted(T['COST'].items()):
        cost += [(stat_index_of(hh), int(s), id_of('COST')(h))
                 for s, h in sorted(slots.items(), key=lambda kv: int(kv[0]))]
    out.append(('COST', cost))
    out.append(('MSNF', rows('MSNF', T['MSNF'])))
    out.append(('OBJV', rows('OBJV', T['OBJV'])))
    out.append(('DRCS', rows('DRCS', T['DRCS'])))
    out.append(('DRGR', rows('DRGR', T['DRGR'])))
    out.append(('REVW', [(int(k.split(',')[0]), int(k.split(',')[1]), id_of('REVW')(h))
                         for k, h in sorted(T['REVW'].items())]))
    out.append(('XPNT', rows('XPNT', T['XPNT'])))
    out.append(('TRIV', [(int(k.split(',')[0]), int(k.split(',')[1]), id_of('TRIV')(h))
                         for k, h in sorted(T['TRIV'].items())]))
    out.append(('ZONE', rows('ZONE', T['ZONE'])))
    enhc = T['ENHC']
    out.append(('IOWN', [(d, k, id_of('ENHC')(enhc[r]) if 0 <= r < len(enhc) else 0)
                         for d, recs in enumerate(T['ITEM_own']) for k, r in enumerate(recs)]))
    out.append(('TOWN', [(t, k, id_of('ENHC')(enhc[r]) if 0 <= r < len(enhc) else 0)
                         for t, recs in enumerate(T['TRIT_own']) for k, r in enumerate(recs)]))
    return out


def write_legacy_lcm(model, cat):
    """model: the era model (legacy.load_eras); cat: the master Catalogue. One era block per content version,
    ascending, each carrying the era's fully resolved tables (as legacy.Era resolves them); the reference era is
    the block whose content version equals the legacy map id."""
    ref = model['reference']
    ref_cv = int(ref.get('content_version') or max(int(k) for k in model['eras']))
    body = b''
    cvs = sorted((int(k) for k in model['eras']))
    for cv in cvs:
        era = legacymod.Era(model, cv)
        b = _u32(cv)
        tabs = _lcm_tables_with_ids(era.tables, cat, ref['STAT'])
        b += _u32(len(tabs))
        for tag, rows in tabs:
            b += tag.encode('ascii') + _u32(len(rows))
            for g, p, i in rows:
                b += _u32(g) + _u32(p) + _u32(i)
        b += _u32(len(era.zone_deltas))
        for zh, d in sorted(era.zone_deltas.items()):
            zid = cat.lookup('ZONE', zh)
            if zid is None:
                raise LCFileError(f'legacy.lcm: zone hash {zh[:16]}... is not in the catalogue')
            m, amb = d['map'], d.get('ambiguous', [])
            b += _u32(zid) + _u32(len(m)) + b''.join(_u32(x) for x in m)
            b += _u32(len(amb)) + b''.join(_u32(x) for x in amb)
        b += _u32(len(era.hero_shared_holdable))
        for hh, positions in sorted(era.hero_shared_holdable.items()):
            sid = cat.lookup('STAT', hh)
            if sid is None:
                raise LCFileError(f'legacy.lcm: holdable hero hash {hh[:16]}... is not in the catalogue')
            b += _u32(sid) + _u32(len(positions)) + b''.join(_u32(x) for x in positions)
        b += _str((era.conversation_digest or '').encode('ascii'))
        b += _u32(era.hero_count)
        ranges = era.tables['ENHC_ranges']
        own = (ranges['trit'][1], len(era.tables['ENHC']))
        for pair in (ranges['prefix'], ranges['suffix'], ranges['trit'], own):
            b += _u32(pair[0]) + _u32(pair[1])
        body += b
    # checks (SPEC 5.3 / 5.4 step 3): the reference build's fingerprint counts
    body += _u32(ref['hero_count']) + _u32(len(ref['DRCS'])) + _u32(len(ref['DRGR'])) + _u32(len(ref['OBJV']))
    return _with_header(LCM_MAGIC, (ref_cv, cat.revision, len(cvs)), body)



def read_legacy_lcm(buf):
    r = _Reader(buf, 'legacy.lcm')
    map_id, cat_revision, era_count = _header_check(r, LCM_MAGIC, 0, 0, 0)
    eras = []
    for _ in range(era_count):
        cv = r.u32()
        tables = {}
        for _ in range(r.u32()):
            tag = r.take(4).decode('ascii')
            if tag not in DOMAIN_NUMBER and tag not in LCM_PSEUDO:
                raise LCFileError(f'legacy.lcm: unknown table tag {tag!r}')
            tables[tag] = [(r.u32(), r.u32(), r.u32()) for _ in range(r.u32())]
        zones = {}
        for _ in range(r.u32()):
            zid = r.u32()
            m = [r.u32() for _ in range(r.u32())]
            amb = [r.u32() for _ in range(r.u32())]
            zones[zid] = {'map': m, 'ambiguous': amb}
        holdable = {}
        for _ in range(r.u32()):
            sid = r.u32()
            holdable[sid] = [r.u32() for _ in range(r.u32())]
        digest = r.s().decode('ascii')
        hero_count = r.u32()
        ranges = {k: (r.u32(), r.u32()) for k in ('prefix', 'suffix', 'trit', 'own')}
        eras.append({'content_version': cv, 'tables': tables, 'zones': zones, 'hero_shared_holdable': holdable,
                     'conversation_digest': digest, 'hero_count': hero_count, 'enhc_ranges': ranges})
    checks = {'hero_blocks': r.u32(), 'courses': r.u32(), 'grades': r.u32(), 'objectives': r.u32()}
    r.done()
    return {'map_id': map_id, 'catalogue_revision': cat_revision, 'eras': eras, 'checks': checks}


# ------------------------------------------------------------------------------------------------ the build's bind lists
def _file_sha1(path):
    with open(path, 'rb') as f:
        return hashlib.sha1(f.read()).digest()


def _load(build, *parts):
    for ext in ('.engb', '.xmlb', '.XMLB'):
        p = os.path.join(build, *parts) + ext
        if os.path.isfile(p):
            return p
    raise LCFileError(f'no data file for {os.path.join(*parts)} under {build}')


def key_text_index(b):
    """{domain tag: {key hash: canonical key bytes}} of everything the build's data names (for catalogue.lcc and
    the .lcbind keys)"""
    out = {t: {} for t in DOMAIN_NUMBER}

    def put(tag, fields):
        if fields and all(f is not None for f in fields):
            out[tag][key_hash(*fields)] = canonical_key(*fields)
    for i in range(len(b.stat)):
        put('STAT', b.key_stat(i))
    for i in range(len(b.item)):
        put('ITEM', b.key_item(i))
    for i in range(len(b.enhancement)):
        put('ENHC', b.key_enh(i))
    for i in range(len(b.name_a)):
        put('NAMA', b.key_name_a(i))
    for c, lst in b.name_b.items():
        for i in range(len(lst)):
            put('NAMB', b.key_name_b(c, i))
    for i in range(len(b.trit)):
        put('TRIT', b.key_trit(i))
    for n in b.shared_talent:
        put('TALN', ('shared', n))
    for h, lst in b.hero_talent.items():
        for n in lst:
            put('TALN', (h, n))
    for h in b.costume:
        for s in range(9):
            put('COST', b.key_costume(h, s))
    for f in b.mission_file:
        put('MSNF', (f,))
    for i in range(len(b.objective)):
        put('OBJV', b.key_objective(i))
    for i in range(len(b.course)):
        put('DRCS', b.key_course(i))
    for i in range(len(b.grade)):
        put('DRGR', b.key_grade(i))
    for (c, i) in b.review:
        put('REVW', b.key_review(c, i))
    for i in range(len(b.xpoint)):
        put('XPNT', b.key_xpoint(i))
    for (a, i) in b.trivia:
        put('TRIV', b.key_trivia(a, i))
    for z in b.zone_names:
        put('ZONE', b.key_zone(z))
    return out


def bind_files(build, cat=None):
    """{relative .lcbind path: bytes} for every save-bound data file of the build, and the problems found:
    ({rel: bytes}, [problem]). A key the catalogue does not know gets id 0 (SPEC 3.4 b: saved as a key
    reference); for the builder's own build that is a problem the validator (V39) reports."""
    cat = cat or catmod.Catalogue.load()
    b = bindsmod.Binds(build)
    texts = key_text_index(b)
    problems = []

    def row(tag, group, position, fields):
        h = key_hash(*fields)
        ident = cat.lookup(tag, h)
        if ident is None:
            ident = 0
            problems.append(f'{tag} {canonical_key(*fields).decode("cp1252", "replace")}: not in the catalogue')
        return (group, position, ident, canonical_key(*fields))

    out = {}

    def emit(path, lists):
        out[os.path.relpath(path, build).replace(os.sep, '/')[:-5] + '.lcbind'] = write_lcbind(_file_sha1(path), lists)

    p = _load(build, 'Data', 'items')
    items = []
    for i in range(len(b.item)):
        cls = (b.item_class[i] or '').lower()
        items.append(row('ITEM', NAMB_CATEGORIES.get(cls, 0), i, b.key_item(i)))
    enhc = [row('ENHC', 0, i, b.key_enh(i)) for i in range(len(b.enhancement))]
    nama = [row('NAMA', 0, i, b.key_name_a(i)) for i in range(len(b.name_a))]
    namb = []
    for cls, lst in sorted(b.name_b.items()):
        cnum = NAMB_CATEGORIES.get(cls.lower())
        if cnum is None:
            problems.append(f'NAMB category {cls!r} is not belt / gloves / armor')
            continue
        namb += [row('NAMB', cnum, i, b.key_name_b(cls, i)) for i in range(len(lst))]
    trit = [row('TRIT', 0, i, b.key_trit(i)) for i in range(len(b.trit))]
    emit(p, [('ITEM', items), ('ENHC', enhc), ('NAMA', nama), ('NAMB', namb), ('TRIT', trit)])

    p = _load(build, 'Data', 'herostat')
    stat = [row('STAT', 0, i, b.key_stat(i)) for i in range(1, b.hero_count + 1)]
    cost = []
    for hero in sorted(b.costume):
        gi = b.stat.index(hero)
        cost += [row('COST', gi, s, b.key_costume(hero, s)) for s in range(9)]
    emit(p, [('STAT', stat), ('COST', cost)])

    p = _load(build, 'Data', 'npcstat')
    emit(p, [('STAT', [row('STAT', 0, i, b.key_stat(i)) for i in range(b.hero_count + 1, len(b.stat))])])

    p = _load(build, 'Data', 'shared_talents')
    emit(p, [('TALN', [row('TALN', 0, i, ('shared', n)) for i, n in enumerate(b.shared_talent)])])

    for hero in sorted(b.hero_talent):
        try:
            p = _load(build, 'Data', 'talents', hero.lower())
        except LCFileError:
            continue                        # a herostat entry without a talent file (e.g. 'default') holds no
        gi = b.stat.index(hero)             # hero talents, so there is nothing to bind
        emit(p, [('TALN', [row('TALN', gi, i, (hero, n)) for i, n in enumerate(b.hero_talent[hero])])])

    p = _load(build, 'Data', 'missions', 'missions')
    emit(p, [('MSNF', [row('MSNF', 0, i, (f,)) for i, f in enumerate(b.mission_file)])])
    for fi, f in enumerate(b.mission_file):
        p = _load(build, 'Data', 'missions', f)
        rows = [row('OBJV', fi, i, b.key_objective(i))
                for i in range(len(b.objective)) if b.objective[i][0] == f]
        emit(p, [('OBJV', rows)])

    p = _load(build, 'Data', 'dangerroom')
    drgr = [row('DRGR', 0, i, b.key_grade(i)) for i in range(len(b.grade))]
    drcs = [row('DRCS', b.course_grade[i], i, b.key_course(i)) for i in range(len(b.course))]
    emit(p, [('DRGR', drgr), ('DRCS', drcs)])

    p = _load(build, 'Data', 'review_paths')
    revw = [row('REVW', c, i, b.key_review(c, i)) for (c, i) in sorted(b.review)]
    emit(p, [('REVW', revw)])

    p = _load(build, 'Data', 'xtraction_points')
    emit(p, [('XPNT', [row('XPNT', 0, i, b.key_xpoint(i)) for i in range(len(b.xpoint))])])

    p = _load(build, 'Data', 'trivia')
    triv = [row('TRIV', a, i, b.key_trivia(a, i)) for (a, i) in sorted(b.trivia)]
    emit(p, [('TRIV', triv)])

    return out, problems


def write_build_files(build, content_version, cat=None, model=None):
    """the whole save-file set of a build: {relative path: bytes} - catalogue.lcc, legacy.lcm and every
    .lcbind - plus the catalogue problems (keys of the build the catalogue does not know)."""
    cat = cat or catmod.Catalogue.load()
    model = model or legacymod.load_eras()
    b = bindsmod.Binds(build)
    files, problems = bind_files(build, cat)
    files[CATALOGUE_LCC.replace(os.sep, '/')] = write_catalogue_lcc(cat, key_text_index(b), content_version)
    files[LEGACY_LCM.replace(os.sep, '/')] = write_legacy_lcm(model, cat)
    return files, problems


# ------------------------------------------------------------------------------------------------ the content fingerprint (decision D5)
def content_fingerprint(build):
    """SHA-256 over the sorted (relative path lower-cased, SHA-1) of the build's catalogue.lcc and every
    .lcbind under Data (SPEC 70; decision D5: co-op peers must run the same content version AND fingerprint).
    legacy.lcm is not part of it: it is converter input, identical for every player of a release, and a co-op
    session never converts. -> 64 hex characters, or None when the build carries no save files yet."""
    root = os.path.join(build, 'Data')
    names = [os.path.join(build, CATALOGUE_LCC)]
    names += glob.glob(os.path.join(root, '**', '*.lcbind'), recursive=True)
    names = [n for n in names if os.path.isfile(n)]
    if not names:
        return None
    h = hashlib.sha256()
    for p in sorted(names, key=lambda n: os.path.relpath(n, build).replace(os.sep, '/').lower()):
        rel = os.path.relpath(p, build).replace(os.sep, '/').lower()
        h.update(rel.encode('utf-8') + b'\0' + _file_sha1(p))
    return h.hexdigest()
