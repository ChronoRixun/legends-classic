"""xml1build.npc_values_selftest - SPEC 24: XML1 value codes in the NPC styles and the NPC energy pool.

usage (from tools/): python -m xml1build.npc_values_selftest [--out <build>] [--base "<XML2 folder>"]
  T1 the value name table and the energy constants against XMen2.exe and default.xbe (byte for byte)
  T2 the same facts re-read from the disassemblies (research/scripts/xml2_text.asm, xml1_text.asm): XMen2.exe's
     resolver compares 5 names and returns 0.0; XML1 resolves every code of data/values.xml while parsing
     (powerusage / damage / knockback readers); both energy formulas; XML1's AI waits for half its energy
  T3 XML2 retail: no style holds a value code (so XMen2.exe never needed more than its 5 names); XML1's and
     XML2's values tables agree on every L/M/H/K code; the XML1 NPC styles XML2 re-ships carry XML1's numbers
     where XML2 kept the move (damage / knockback parity)
  T4 every XML1 NPC style characters writes (x1schema + convert_npc_powerups + resolve_style): no code left,
     idempotent, counts per attribute; Pyro's flame 15..18, fire ring M2 / K6, the Sabretooth / Toad examples
  T5 the energy talent: for every converted XML1 stats entry XMen2.exe's formulas + the talent == XML1's pool and
     regeneration; the definition passes talent_problems; attach_energy_talent is idempotent; name lengths
  T6 (--out) V19 read-only over that build: 0 errors; PyroAct1's rank, x1_ps_pyro's flame damage
Writes nothing. Never launches the game.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xml1build import common as C                # noqa: E402
from xml1build import combat_events as CE        # noqa: E402
from xml1build import heroes as H                # noqa: E402
from xml1build import npc_values as NV           # noqa: E402
from xml1build import x1schema as XS             # noqa: E402
import xmlb                                      # noqa: E402

X1_DATA = ASM2 = ASM1 = XBE = None


def use_sources(src):
    """read the XML1 data, default.xbe and the disassemblies through a Sources (SPEC 27): main() passes the --out
    build's (Sources.for_out: its _build/sources.json, else developer mode)."""
    global X1_DATA, ASM2, ASM1, XBE
    X1_DATA = src.x1_loose / 'data'
    ASM2 = src.research / 'scripts' / 'xml2_text.asm'
    ASM1 = src.research / 'scripts' / 'xml1_text.asm'
    XBE = src.x1_xbox / 'default.xbe'


use_sources(C.Sources.developer())
# disassembly lines the engine facts rest on (address -> the line's text after the address)
ASM2_FACTS = {
    '004c4670': 'push 0x68f2fc ; "data/values.xmlb"',          # 0x4c4640 loads data/values.xmlb
    '004c47b1': 'cmp esi, 0x6da268',                            # ... and keeps the 5 rows of 0x6da240 only
    '004c48c0': 'mov edx, dword ptr [edi*8 + 0x6da244]',        # 0x4c4870 compares a name with the 5 names
    '004c48d6': 'cmp edi, 5',
    '004c48e9': 'fld dword ptr [0x680030]',                     # ... else returns 0.0
    '004c493f': 'push 0x681aac ; "%f %f"',                      # a number with a blank: min and max
    '004dadca': 'call 0x4c1dd0',                                # powerusage -> the talent-value parser
    '004b8cf8': 'fmul dword ptr [0x6d9778]',                    # max energy: 4 x level
    '004b8d02': 'fld dword ptr [0x6d977c]',                     # ... + 2 x mind
    '0042cd47': 'fadd dword ptr [0x683f2c]',                    # enemy regeneration base 15
    '004f60dc': 'call dword ptr [eax + 0x20]',                  # canAfford sums the trigger costs
}
ASM1_FACTS = {
    '000b812b': 'push 0x3d43bc ; "data/values.xml"',            # 0xb8100 loads data/values.xml
    '000b7ec3': 'call 0x1186a0',                                # 0xb7e60 looks the name up in the table
    '000b7ee4': 'fld dword ptr [esi + eax*8 + 0x994]',          # ... and returns its min
    '000cdc3a': 'call 0xb8550',                                 # powerusage parsed through the value table
    '000cf6e9': 'call 0xb8550',                                 # attack Damage (min + max)
    '000d7c20': 'call 0xb8550',                                 # knockback
    '000afc0f': 'fmul dword ptr [0x44f204]',                    # max energy: 4 x level
    '000afc19': 'fld dword ptr [0x44f208]',                     # ... + 7 x mind
    '000af87e': 'fmul dword ptr [0x3c93c0]',                    # regeneration x (1 + 0.01 mind)
    '0003aa5c': 'fadd dword ptr [0x3c836c]',                    # non-hero regeneration base 15
    '000cdef3': 'call 0x3f410',                                 # every powerusage trigger spends
    '000e1ac1': 'call 0x2e8c0',                                 # canAfford: energy vs the summed cost
    '000ee398': 'fcomp dword ptr [0x3c9404]',                   # AI: no power below half the energy (2.0)
}
# XML1 NPC styles XML2 retail re-ships under the same name (T3 parity)
PARITY_STYLES = ('ps_sabretooth', 'ps_pyro', 'ps_blob', 'ps_toad', 'ps_juggernaut', 'ps_magneto', 'ps_mystique',
                 'ps_sentinel', 'ps_archangel', 'ps_bishop')

fails = []


def check(cond, msg):
    print(('  ok   ' if cond else '  FAIL ') + msg, flush=True)
    if not cond:
        fails.append(msg)


def rel_of(p):
    return 'data/' + p.relative_to(X1_DATA).as_posix().lower()


def asm_lines(path, want):
    got = {}
    if not path.exists():
        return None
    keys = set(want)
    with open(path, encoding='latin-1') as f:
        for line in f:
            a = line[:8]
            if a in keys:
                got[a] = line[9:].rstrip('\n')
    return got


def npc_style_files(base):
    """the XML1 styles characters writes (every .eng/.xml whose mapped name XML2 does not ship), minus the hero
    styles the heroes module rewrites: [(path, kind)]."""
    heroes = {(s.get('powerstyle') or '').lower() for s in C.parse_x1_text(X1_DATA / 'herostat.eng').iter()
              if s.get('powerstyle')}
    heroes |= {(s.get('powerstyle') or '').lower() for s in C.parse_x1_text(X1_DATA / 'npcstat.eng').iter()
               if (s.get('name') or '').lower() in {n.lower() for n in H.ROSTER_NPC}}
    out, seen = [], set()
    for kind in ('powerstyles', 'fightstyles'):
        for p in sorted((X1_DATA / kind).iterdir()):
            if p.suffix.lower() not in ('.eng', '.xml') or (kind, p.stem.lower()) in seen:
                continue
            seen.add((kind, p.stem.lower()))
            stem = p.stem.lower()
            mapped = C.map_powerstyle(stem) if kind == 'powerstyles' else C.map_fightstyle(stem)
            if (base / 'Data' / kind / f'{mapped}.XMLB').exists() or stem in heroes:
                continue
            out.append((p, kind))
    return out


def convert(p, values):
    r = C.parse_x1_text(p)
    XS.convert(r, rel_of(p))
    H.convert_npc_powerups(r, values, f'{p.stem}:')
    return r


def move(r, name):
    return next((m for m in r.iter('FightMove') if (m.get('name') or m.get('Name') or '').lower() == name), None)


def attr(el, name):
    k = next((k for k in el.attrib if k.lower() == name), None)
    return el.get(k) if k else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    ap.add_argument('--base', default=str(C.DEFAULT_BASE))
    a = ap.parse_args(argv)
    base = Path(a.base)
    use_sources(C.Sources.for_out(a.out, base) if a.out else C.Sources.developer(base))
    values = H.Values(C.parse_x1_text(X1_DATA / 'values.xml'))

    print('T1 exe / xbe facts')
    bad = NV.verify_exe(base / 'XMen2.exe')
    check(not bad, f'XMen2.exe: value names {list(NV.EXE_VALUE_NAMES)} at 0x{NV.VALUE_NAME_TABLE:x}, the 5-name '
                   f'loop, energy constants {sorted(hex(k) for k in NV.X2_FLOATS)} {bad[:3]}')
    if XBE.exists():
        bad = NV.verify_xbe(XBE)
        check(not bad, f'default.xbe: value table vtable 0x3d4380 (resolver 0xb7e60), energy constants '
                       f'{sorted(hex(k) for k in NV.X1_FLOATS)} {bad[:3]}')
    else:
        print(f'  skip {XBE} absent')

    print('T2 disassembly facts')
    for path, facts in ((ASM2, ASM2_FACTS), (ASM1, ASM1_FACTS)):
        got = asm_lines(path, facts)
        if got is None:
            print(f'  skip {path} absent')
            continue
        miss = {k: (v, got.get(k)) for k, v in facts.items() if got.get(k) != v}
        check(not miss, f'{path.name}: {len(facts)} lines as recorded {miss}')

    print('T3 XML2 retail: no codes; values tables; ported NPC parity')
    n, codes = 0, collections.Counter()
    for d in ('powerstyles', 'fightstyles'):
        for p in sorted((base / 'Data' / d).iterdir()):
            if p.suffix.lower() not in ('.xmlb', '.engb'):
                continue
            n += 1
            found, exe_codes = NV.code_findings(xmlb.decode(p.read_bytes()))
            codes.update(f'{p.stem}:{v}' for *_x, v in found)
            codes.update(f'{p.stem}:{k}' for k in exe_codes)
    sn, sx = NV.code_findings(xmlb.decode((base / 'Data' / 'shared_nodes.XMLB').read_bytes()))
    check(n >= 150 and not codes and not sn and not sx, f'{n} XML2 retail style files + shared_nodes: no value-code '
                                                       f'shaped attribute value {dict(codes)}')
    x2v = {v.get('name'): (v.get('min'), v.get('max')) for v in xmlb.decode((base / 'Data' / 'values.XMLB')
                                                                            .read_bytes()).iter('value')}
    lmhk = [k for k in values.table if re.match(r'^[LMHK]\d', k)]
    diff = [k for k in lmhk if x2v.get(k) != values.table[k]]
    check(len(lmhk) >= 50 and not diff, f'{len(lmhk)} L/M/H/K codes: XML1 values.xml == XML2 values.XMLB {diff}')
    pdiff = sorted({k for k in values.table if re.match(r'^P\d+$', k) and x2v.get(k) and
                    int(x2v[k][0]) * 10 != int(values.table[k][0])})
    check(not pdiff, f'XML2 P codes are XML1\'s / 10 (P5: XML1 {values.table["P5"][0]}, XML2 {x2v["P5"][0]}) {pdiff}')
    same, differ, other = collections.Counter(), [], collections.Counter()
    for stem in PARITY_STYLES:
        p1 = next((X1_DATA / 'powerstyles' / f'{stem}{e}' for e in ('.eng', '.xml')
                   if (X1_DATA / 'powerstyles' / f'{stem}{e}').exists()), None)
        p2 = base / 'Data' / 'powerstyles' / f'{stem}.XMLB'
        if p1 is None or not p2.exists():
            continue
        r1 = C.parse_x1_text(p1)
        NV.resolve_style(r1, values)
        r2 = xmlb.decode(p2.read_bytes())
        ev2 = {(e.get('name') or '').lower(): e for e in r2 if e.tag == 'event'}
        for e in r1:
            if e.tag.lower() != 'event' or (attr(e, 'name') or '').lower() not in ev2:
                continue
            for k in ('damage', 'knockback'):
                v1, v2 = attr(e, k), ev2[(attr(e, 'name') or '').lower()].get(k)
                if v1 and v2 and not v2.startswith('%'):
                    (same.update([k]) if v1 == v2 else differ.append(f'{stem}:{attr(e, "name")} {k} {v1}/{v2}'))
        m2 = {(m.get('name') or '').lower(): m for m in r2.iter('FightMove')}
        for m1 in r1.iter('FightMove'):
            mm = m2.get((attr(m1, 'name') or '').lower())
            if mm is None:
                continue
            t2 = [t for t in mm if t.tag == 'trigger']
            for t1 in (t for t in m1 if t.tag.lower() == 'trigger'):
                u = next((t for t in t2 if t.get('time') == attr(t1, 'time') and
                          (t.get('name') or '') == (attr(t1, 'name') or '') and t.get('tag') == attr(t1, 'tag')), None)
                if u is None:
                    continue
                for k in ('damage', 'knockback', 'powerusage'):
                    v1, v2 = attr(t1, k), u.get(k)
                    if not v1 or not v2 or v2.startswith('%'):
                        continue
                    if k == 'powerusage':
                        other['powerusage XML2 = XML1 / 10' if abs(float(v2) * 10 - float(v1)) < 1e-6
                              else 'powerusage other'] += 1
                    elif v1 == v2:
                        same[k] += 1
                    else:
                        differ.append(f'{stem}:{attr(m1, "name")} {k} {v1}/{v2}')
    check(sum(same.values()) >= 15 and sum(same.values()) > 2 * len(differ),
          f'XML2 retail re-ships XML1 NPC moves with XML1\'s resolved numbers: {dict(same)} equal, {len(differ)} '
          f'rebalanced by XML2 {differ[:6]}; {dict(other)}')

    print('T4 every XML1 NPC style characters writes')
    files = npc_style_files(base)
    total, left, probs, idem = collections.Counter(), [], [], True
    styles_with = 0
    for p, kind in files:
        r = convert(p, values)
        before, _ = NV.code_findings(r)
        c, pr = NV.resolve_style(r, values, f'{p.stem}:')
        probs += pr
        total.update(c)
        styles_with += bool(before)
        snap = ET.tostring(r)
        again, _ = NV.resolve_style(r, values)
        idem &= not again and ET.tostring(r) == snap
        found, exe_codes = NV.code_findings(r)
        left += [f'{p.stem}:{w} <{t} {k}="{v}">' for w, t, k, v in found]
        left += [f'{p.stem}: {k}' for k in exe_codes]
    attrs = {k: v for k, v in total.items() if not k.startswith('code:')}
    check(len(files) >= 60 and not left and not probs,
          f'{len(files)} NPC styles: {sum(attrs.values())} codes in {styles_with} styles resolved {attrs}, none left '
          f'{left[:3]} {probs[:3]}')
    check(idem, 'a second resolve_style changes nothing (idempotent)')
    check(attrs.get('damage', 0) > 200 and attrs.get('knockback', 0) > 50 and attrs.get('powerusage', 0) > 100,
          'damage > 200, knockback > 50, powerusage > 100 (the census that read as 0)')
    pyro = convert(X1_DATA / 'powerstyles' / 'ps_pyro.eng', values)
    NV.resolve_style(pyro, values)
    fd = next(e for e in pyro if e.tag == 'event' and e.get('name') == 'flame_dmg')
    ring = [t for t in move(pyro, 'firering1') if t.tag == 'trigger' and t.get('name') == 'fire_ring']
    pu = next(t for t in move(pyro, 'firering1') if t.tag == 'trigger' and t.get('name') == 'powerusage')
    check(attr(fd, 'damage') == '15 18', f"Pyro flame_dmg damage L3 -> {attr(fd, 'damage')} (XML2 retail ps_pyro: "
                                         f"'15 18')")
    check([(attr(t, 'damage'), attr(t, 'knockback')) for t in ring] ==
          [('100 125', '370'), ('80 100', '245'), ('50 63', '190')] and attr(pu, 'powerusage') == '50',
          f'Pyro fire ring M2/K6, M1/K4, L5/K3 and its P5 cost: '
          f'{[(attr(t, "damage"), attr(t, "knockback")) for t in ring]} {attr(pu, "powerusage")}')
    toad = convert(X1_DATA / 'powerstyles' / 'ps_toad.eng', values)
    NV.resolve_style(toad, values)
    tl = sorted({(k.lower(), v) for e in toad.iter() for k, v in e.attrib.items()
                 if k.lower() in ('damage', 'knockback', 'powerusage')})
    check(not [x for x in tl if NV.is_code(x[1])], f'Toad: {tl[:6]} ...')

    print('T5 the NPC energy talent')
    stats = [s for f in ('npcstat.eng', 'herostat.eng') for s in C.parse_x1_text(X1_DATA / f).iter()
             if s.tag.lower() == 'stats']
    worst, n, top = [], 0, 0
    for s in stats:
        lv = NV._int_attr(s, 'level') or 1
        m = NV._int_attr(s, 'mind') or 0
        r = NV.energy_rank(s)
        if not r:
            if NV.x2_max_energy(lv, m) != NV.x1_max_energy(lv, m):
                worst.append((attr(s, 'name'), 'no rank but the pools differ'))
            continue
        n += 1
        top = max(top, r)
        if r == m and (NV.x2_max_energy(lv, m, r) != NV.x1_max_energy(lv, m) or
                       abs(NV.x2_regen(r) - NV.x1_regen(m)) > 1e-9):
            worst.append((attr(s, 'name'), NV.x2_max_energy(lv, m, r), NV.x1_max_energy(lv, m)))
    check(n > 100 and not worst, f'{n} XML1 stats entries with a mind (ranks 1..{top}): XMen2.exe max energy + '
                                 f'talent == XML1\'s 30 + 4L + 7M, regeneration 15 x rank-scale == XML1\'s '
                                 f'15 x (1 + M/100) {worst[:3]}')
    pyro_st = next(s for s in stats if (attr(s, 'name') or '').lower() == 'pyroact1')
    check((NV.x1_max_energy(9, 13), NV.x2_max_energy(9, 13), NV.x2_max_energy(9, 13, NV.energy_rank(pyro_st))) ==
          (157, 92, 157), 'PyroAct1 (L9 M13): XML1 157, XMen2.exe alone 92, with the talent 157 (fire ring costs 50)')
    t = NV.energy_talent(top)
    check(not NV.talent_problems(t, top) and NV.talent_problems(t, top + 1),
          f'definition for ranks 1..{top} passes talent_problems (and fails for {top + 1})')
    check(len(NV.TV_MAX) <= H.TALENTVALUE_NAME_MAX and len(NV.TV_REGEN) <= H.TALENTVALUE_NAME_MAX and
          len(NV.ENERGY_TALENT) <= 31 and all(x.get('attribute') in CE.AFFECTERS for x in t.iter('affecter')),
          f'talentvalue names <= {H.TALENTVALUE_NAME_MAX} chars, affecters registered in XMen2.exe')
    st = ET.Element('stats', {'name': 'zz', 'mind': '20', 'level': '5'})
    r1 = NV.attach_energy_talent(st)
    snap = ET.tostring(st)
    r2 = NV.attach_energy_talent(st)
    st0 = ET.Element('stats', {'name': 'zz', 'level': '5'})
    check(r1 == r2 == 20 and ET.tostring(st) == snap and NV.attach_energy_talent(st0) is None and not len(st0),
          'attach_energy_talent: rank = mind, idempotent, none without a mind')

    if a.out:
        print(f'T6 V19 over {a.out} (read-only)')
        out = Path(a.out)
        v = _ReadOnlyValidator(out, base)
        ck = _Check()
        NV.v19(v, ck)
        for e in ck.errors[:10]:
            print('    ' + e)
        check(not ck.errors, f'V19: {len(ck.errors)} errors, counts {dict(ck.counts)}')
        npc = v.tree('Data/npcstat.engb')
        p1 = next((s for s in npc.iter('stats') if (s.get('name') or '').lower() == 'pyroact1'), None)
        rk = [x.get('level') for x in p1 if x.tag == 'talent' and x.get('name') == NV.ENERGY_TALENT] if p1 is not None \
            else None
        ps = v.tree('Data/powerstyles/x1_ps_pyro.XMLB')
        fd = next((e for e in ps if e.tag == 'event' and e.get('name') == 'flame_dmg'), None) if ps is not None else None
        check(rk == ['13'] and fd is not None and fd.get('damage') == '15 18',
              f'PyroAct1 {NV.ENERGY_TALENT} rank {rk}; x1_ps_pyro flame_dmg damage '
              f'{fd.get("damage") if fd is not None else None}')

    print('FAIL' if fails else 'PASS', f'({len(fails)} failures)')
    return 1 if fails else 0


class _Check:
    def __init__(self):
        self.errors, self.warnings, self.notes, self.allowed = [], [], [], []
        self.counts = collections.Counter()

    def error(self, m):
        self.errors.append(m)

    def warn(self, m):
        self.warnings.append(m)

    def note(self, m):
        self.notes.append(m)

    def allow(self, m, why):
        self.allowed.append((m, why))

    def count(self, k, n=1):
        self.counts[k] += n

    def set(self, k, n):
        self.counts[k] = n


class _ReadOnlyValidator:
    """the part of validate.Validator V19 uses, over an existing build (its registry.json), without a ctx."""

    def __init__(self, out, base):
        self.ctx = type('Ctx', (), {'base': base, 'out': out})()
        self.idx = C.FileIndex(out, exclude_top=C.META_NAMES)
        reg = json.loads((out / '_build' / 'registry.json').read_text(encoding='utf-8'))
        self.reg = {C.norm(k): e for k, e in reg.get('entries', {}).items()}
        self._trees = {}

    def entry(self, rel):
        return self.reg.get(C.norm(rel))

    def tree(self, rel):
        n = C.norm(rel)
        if n not in self._trees:
            p = self.idx.path(rel)
            self._trees[n] = xmlb.decode(p.read_bytes()) if p is not None else None
        return self._trees[n]

    def stats(self):
        st = {'variants': {}}
        for ext in ('.engb', '.xmlb'):
            st['variants'][ext] = {f: (list(t.iter('stats')) if (t := self.tree(f'data/{f}{ext}')) is not None else [])
                                   for f in ('herostat', 'npcstat')}
        return st

    def x1_stats(self):
        d = {}
        for f in ('herostat', 'npcstat'):
            for el in C.parse_x1_text(X1_DATA / f'{f}.eng').iter('stats'):
                d[(el.get('name') or '').lower()] = (f, el)
        return d


if __name__ == '__main__':
    sys.exit(main())
