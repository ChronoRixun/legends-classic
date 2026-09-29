"""xml1build.combat_events_selftest - standalone self-test of combat_events (SPEC 22). Not part of the build.

usage (from tools/): python -m xml1build.combat_events_selftest [--out <build>] [--base "<XML2 folder>"]

  T1 the registered tables match the install's XMen2.exe (push 68 <imm32> at each address, the string at its VA;
     the affecter table rows)
  T2 the tables equal a fresh read of research/scripts/xml2_text.asm (skipped when the listing is absent)
  T3 the resolver on XML2's 131 retail styles (XMLB): only XML2's own known defects are unresolved (no false positives)
  T4 XML1 census: before the rewrite exactly the known unresolved names; after it only the allowlisted XML1 no-ops,
     and every unregistered FightMove handler is assessed (UNREGISTERED_HANDLER_NOTES)
  T5 the rewrite is idempotent on every XML1 style and changes exactly 8 events / 8 damageMods / 3 handlers
  T6 Magma: lava_rift (power2 Lava Fissure) resolves to ce_atk_blast after x1schema.convert, keeps its own
     damageMod and gains XML1 blast_ranged's dmgmod_popup; Gambit / Jubilee charged_throw -> ch_pickup_throw
  T7 negative: a synthetic style with one defect of each kind -> every finding reported
  T8 (--out) V18 over that build, read-only: 0 errors; prints Magma's power2 and its resolution
  T9 SPEC 22.7: heroes.convert_npc_powerups over every XML1 NPC style: no XML1-form powerup trigger / removal left,
     the change counts, idempotency, Blob / shadow demon / GRSO elite / Master Mold / Juggernaut / Havok forms, and
     the heroes' converter's special_fx forms (XML1 attributes as XMen2.exe reads them)
Reads only; never writes, never launches the game.
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xml1build import common as C                # noqa: E402
from xml1build import combat_events as CE        # noqa: E402
from xml1build import x1schema as XS             # noqa: E402
import xmlb                                      # noqa: E402

X1_DATA = ASM = None


def use_sources(src):
    """read the XML1 data and the disassembly through a Sources (SPEC 27): main() passes the --out build's
    (Sources.for_out: its _build/sources.json, else developer mode)."""
    global X1_DATA, ASM
    X1_DATA = src.x1_loose / 'data'
    ASM = src.research / 'scripts' / 'xml2_text.asm'


use_sources(C.Sources.developer())
# XML1 names XMen2.exe cannot resolve before the rewrite (7 blast_ranged events + the triggers naming them) and
# the one XML1 no-op; orphan tags that exist only because their parent trigger was one of them
EXPECTED_UNRESOLVED_BEFORE = {'card_impact', 'firework', 'firework_blue', 'lava_impact', 'lava_rift',
                              'lightning_impact', 'orbital_impact', 'psy_knife', 'pickup_sound'}
EXPECTED_CHANGES = {'combat_event:blast_ranged->blast': 8, 'combat_event_damagemod:dmgmod_popup': 8,
                    'combat_handler:ch_throw->ch_pickup_throw': 3,
                    'combat_affecter:atk_damage_scale->atk_damage': 2}     # Jubilee taunt, NPC Mystique
# XML2 retail styles XMen2.exe ships with unresolvable triggers (their own data): stem -> names
# (a trigger with neither name nor tag is reported as 'tag=None')
XML2_RETAIL_UNRESOLVED = {'ps_beast': {'orbital_impact'}, 'ps_sin_wolverine': {'tag=None'}, 'ps_toad': {'tag=None'}}

fails = []


def check(cond, msg):
    print(('  ok   ' if cond else '  FAIL ') + msg, flush=True)
    if not cond:
        fails.append(msg)


def x1_styles():
    files = sorted(p for d in ('powerstyles', 'fightstyles') for p in (X1_DATA / d).iterdir()
                   if p.suffix.lower() in ('.eng', '.xml'))
    return files + [X1_DATA / 'shared_nodes.eng']


def rel_of(p):
    return 'data/' + p.relative_to(X1_DATA).as_posix().lower()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    ap.add_argument('--base', default=str(C.DEFAULT_BASE))
    a = ap.parse_args(argv)
    base = Path(a.base)
    use_sources(C.Sources.for_out(a.out, base) if a.out else C.Sources.developer(base))
    shared = CE.event_table(xmlb.decode((base / 'Data' / 'shared_combat_events.XMLB').read_bytes()))

    print('T1 tables vs XMen2.exe')
    bad = CE.verify_exe(base / 'XMen2.exe')
    check(not bad, f'{len(CE.CE_TYPES)} ce_* types + {len(CE.FM_HANDLERS)} handlers + {len(CE.AFFECTERS)} affecters + '
                   f'%default% verified {bad[:3]}')
    check(len(CE.CE_TYPES) == 70 and len(CE.FM_HANDLERS) == 68 and len(CE.AFFECTERS) == 95,
          '70 ce_* types, 68 FightMove handlers, 95 affecter names')

    print('T2 tables vs the disassembly')
    if ASM.exists():
        d = CE.derive_from_asm(ASM)
        check(d['ce_'] == CE.CE_TYPES, f'factory 0x{CE.CE_FACTORY:x}: {len(d["ce_"])} names re-read, equal')
        check(d['ch_'] == CE.FM_HANDLERS, f'registrar 0x{CE.FM_HANDLER_REGISTRAR:x}: {len(d["ch_"])} names re-read, equal')
    else:
        print(f'  skip {ASM} absent')

    print('T3 resolver on XML2 retail styles')
    got = collections.defaultdict(set)
    n = 0
    for d in ('powerstyles', 'fightstyles'):
        for p in sorted((base / 'Data' / d).iterdir()):
            if p.suffix.lower() != '.xmlb':
                continue
            n += 1
            for f in CE.style_findings(xmlb.decode(p.read_bytes()), shared):
                if f.kind in ('unresolved', 'orphan_tag', 'trigger_cap', 'name_len'):
                    got[p.stem.lower()].add(f.name)
    got = dict(got)
    check(got == XML2_RETAIL_UNRESOLVED, f'{n} retail styles: unresolved only {XML2_RETAIL_UNRESOLVED} (got {got})')
    sn = CE.style_findings(xmlb.decode((base / 'Data' / 'shared_nodes.XMLB').read_bytes()), shared)
    check(not [f for f in sn if f.kind != 'handler'], 'XML2 shared_nodes: every trigger resolves')

    print('T4/T5 XML1 census and rewrite')
    before, after, changes = set(), [], collections.Counter()
    handlers = set()
    idem = True
    for p in x1_styles():
        root = C.parse_x1_text(p)
        if root is None:
            continue
        before |= {f.name for f in CE.style_findings(root, shared) if f.kind == 'unresolved'}
        c = XS.convert(root, rel_of(p))
        changes.update({k: v for k, v in c.items() if k.startswith('combat_')})
        snap = ET.tostring(root)
        again = CE.rewrite_style(root)
        idem &= not again and ET.tostring(root) == snap
        stem = p.stem.lower()
        for f in CE.style_findings(root, shared):
            if f.kind == 'handler':
                handlers.add(f.name)
            elif f.kind not in ('ignored_tag', 'x1_powerup_form', 'x1_powerup_remove', 'x1_powerup_update') and \
                    not CE.allowed(stem, f):
                after.append(f.text(stem))
    check(before == EXPECTED_UNRESOLVED_BEFORE, f'before: unresolved {sorted(before)}')
    check(not after, f'after: nothing unresolved but the allowlisted XML1 no-ops {after[:5]}')
    check(handlers <= set(CE.UNREGISTERED_HANDLER_NOTES), f'unregistered handlers all assessed: {sorted(handlers)}')
    check('ch_throw' not in handlers, 'ch_throw renamed everywhere')
    check(dict(changes) == EXPECTED_CHANGES, f'changes {dict(changes)}')
    check(idem, 'second rewrite changes nothing (idempotent)')

    print('T6 Magma / Gambit / Jubilee')
    mg = C.parse_x1_text(X1_DATA / 'powerstyles' / 'ps_magma.eng')
    XS.convert(mg, 'data/powerstyles/ps_magma.eng')
    ev = next(e for e in mg if e.tag.lower() == 'event' and e.get('name') == 'lava_rift')
    mods = sorted(d.get('name') for d in ev if d.tag.lower() == 'damagemod')
    check(ev.get('inherit') == 'blast' and mods == ['dmgmod_environment', 'dmgmod_popup'],
          f'lava_rift event: inherit={ev.get("inherit")} damageMods={mods} damagetype={ev.get("damagetype")} '
          f'maxrange={ev.get("maxrange")}')
    typ, chain = CE.resolve({k.lower(): v for k, v in ev.attrib.items()}, shared)
    check(typ == 'ce_atk_blast', f'lava_rift -> {" > ".join(chain)} -> {typ}')
    fis = next(m for m in mg if m.tag == 'FightMove' and (m.get('name') or '').lower() == 'fissure1')
    fs = [f for f in CE.style_findings(mg, shared) if f.move.lower() == 'fissure1']
    check(not fs, f'fissure1 (power2 root) triggers all resolve: {[t.get("name") for t in fis if t.tag == "trigger"]}')
    for hero in ('ps_gambit', 'ps_jubilee'):
        r = C.parse_x1_text(X1_DATA / 'powerstyles' / f'{hero}.eng')
        XS.convert(r, f'data/powerstyles/{hero}.eng')
        ct = next(m for m in r if m.tag == 'FightMove' and (m.get('name') or '').lower() == 'charged_throw')
        check(ct.get('handler') == 'ch_pickup_throw', f'{hero} charged_throw handler {ct.get("handler")}')
        if hero == 'ps_jubilee':
            pu = [t for t in r.iter() if t.tag == 'trigger' and t.get('name') == 'powerup' and
                  (t.get('powerup') or '').startswith('atk_damage')]
            check(pu and all(t.get('powerup') == 'atk_damage' and t.get('affect_type') == 'scale' for t in pu),
                  f'ps_jubilee taunt weaken: {[(t.get("powerup"), t.get("affect_type"), t.get("level")) for t in pu]}')

    print('T7 negative')
    neg = ET.fromstring(
        '<powerstyle><event name="ok_ev" inherit="blast"/><event name="bad_ev" inherit="no_such_base"/>'
        '<FightMove name="m1" handler="ch_bogus"><trigger name="no_such_event" time="0"/>'
        '<trigger name="x" type="ce_bogus" time="0"/><trigger tag="7" damage="1"/><trigger time="0"/>'
        '<trigger name="ok_ev" time="0"/><trigger2 name="vel" type="ce_velocity"/>'
        '<trigger name="powerup"><affecter attribute="bogus_attr" level="1"/></trigger>'
        f'<trigger name="{"n" * 32}" type="ce_sound"/></FightMove>'
        '<FightMove name="m2">' + ''.join(f'<trigger name="sound" tag="{i}"/>' for i in range(20)) + '</FightMove>'
        '<FightMove name="m3" inherit="m2"><trigger tag="3" sound="x"/><trigger name="sound" tag="30"/></FightMove>'
        '<FightMove name="p1"><trigger name="powerup" tag="1" powerup="def_damage" level="0" life="-1"/></FightMove>'
        '<FightMove name="p2" inherit="p1"><trigger tag="1" remove="true"/></FightMove>'
        '<FightMove name="p4" inherit="p1"><trigger tag="1" level="A4" life="9"/></FightMove>'
        '<FightMove name="p3"><trigger name="powerup" powerup="invisible" remove="true" time="0"/>'
        '<trigger name="tintin" type="ce_renderfx" remove="true" time="0"/></FightMove>'
        '</powerstyle>')
    fnd = {(f.kind, f.move, f.name) for f in CE.style_findings(neg, shared)}
    want = {('unresolved', '<style>', 'bad_ev'), ('handler', 'm1', 'ch_bogus'), ('unresolved', 'm1', 'no_such_event'),
            ('unresolved', 'm1', 'x'), ('orphan_tag', 'm1', 'tag=7'), ('unresolved', 'm1', 'tag=None'),
            ('ignored_tag', 'm1', 'vel'), ('name_len', 'm1', 'n' * 32), ('trigger_cap', 'm2', '20'),
            ('trigger_cap', 'm3', '21'), ('affecter', 'm1', 'bogus_attr'),
            ('x1_powerup_form', 'p1', 'def_damage'), ('x1_powerup_remove', 'p2', 'tag=1'),
            ('x1_powerup_remove', 'p3', 'tag=None'), ('x1_powerup_update', 'p4', 'tag=1')}
    check(want <= fnd, f'every injected defect found (missing {sorted(want - fnd)})')
    check(not any(k == 'unresolved' and n == 'ok_ev' for k, _m, n in fnd), 'a valid local event resolves')
    check(not any(k == 'orphan_tag' and m == 'm3' for k, m, _n in fnd), 'a tag update of an inherited trigger is fine')
    hk = next(f for f in CE.style_findings(neg, shared) if f.kind == 'handler')
    check(hk.detail == 'UNDOCUMENTED', 'an unassessed handler is marked UNDOCUMENTED (V18 error)')
    rm = [f for f in CE.style_findings(neg, shared) if f.kind == 'x1_powerup_remove']
    check(len(rm) == 2, f'an XML1 ce_renderfx remove="true" is no powerup removal ({[f.text() for f in rm]})')

    t9_npc_powerups(shared)

    if a.out:
        print(f'T8 V18 over {a.out} (read-only)')
        from xml1build import validate as V
        out = Path(a.out)
        v = _ReadOnlyValidator(out, base)
        ck = V.Check('V18', 'combat events')
        CE.v18(v, ck)
        check(not ck.errors, f'V18: {len(ck.errors)} errors, {len(ck.warnings)} warnings, {len(ck.allowed)} allowed '
                             f'{ck.errors[:3]}')
        print('    counts', ck.counts)
        ps = v.tree('Data/powerstyles/ps_magma.XMLB')
        if ps is not None:
            for e in ps:
                if e.tag == 'event' and e.get('name') == 'lava_rift':
                    print(_indent(e))
            p2 = next((m for m in ps if m.tag == 'FightMove' and m.get('name') == 'power2'), None)
            if p2 is not None:
                print(_indent(p2))
                sh = CE.event_table(v.tree(CE.SHARED_EVENTS_REL))
                local = {}
                for e in ps:
                    if e.tag == 'event':
                        t, _ = CE.resolve(dict(e.attrib), local, sh)
                        if t:
                            local[e.get('name').lower()] = (t, dict(e.attrib))
                for t in p2:
                    if t.tag == 'trigger':
                        typ, chain = CE.resolve(dict(t.attrib), local, sh)
                        print(f'    trigger {t.get("name")!r:12} -> {" > ".join(chain)} -> {typ}')
    print(f'\ncombat_events_selftest: {"FAIL" if fails else "PASS"} ({len(fails)} failures)')
    return 1 if fails else 0


# SPEC 22.7: XML1-form powerup triggers in the XML1 NPC styles (the styles characters writes; the heroes' own and
# XML2's same-name moveset_stealth excluded): kind -> count after convert_npc_powerups
EXPECTED_NPC_CHANGES = {
    'npc_powerup:atk_damage': 1, 'npc_powerup:atk_knockback': 1, 'npc_powerup:def_damage': 19,
    'npc_powerup:def_knockback': 1, 'npc_powerup:def_pain': 1, 'npc_powerup:deflect_damage': 1,
    'npc_powerup:health_regen': 5, 'npc_powerup:invisible_class': 1, 'npc_powerup:move': 7, 'npc_powerup:none': 3,
    'npc_powerup:none_attribute': 1, 'npc_powerup:nullify': 1, 'npc_powerup:speed': 2, 'npc_powerup:strength': 2,
    'npc_powerup:touch_damage': 1, 'npc_powerup_remove:def_damage': 6, 'npc_powerup_remove:invisible': 17,
    'npc_powerup_tag_name': 7,
    # XML1 tag updates of an inherited powerup's level / affect_type (Juggernaut x2, Marrow, Avalanche; Mystique's
    # two leave the level as it was) and the later updates retargeted to the replacement (Juggernaut armor_start /
    # armor_end)
    'npc_powerup_update:level': 4, 'npc_powerup_update:affect_type': 1, 'npc_powerup_update_same': 2,
    'npc_powerup_retag': 2}


def _x1_npc_style(stem):
    for d in ('powerstyles', 'fightstyles'):
        for ext in ('.eng', '.xml'):
            p = X1_DATA / d / f'{stem}{ext}'
            if p.exists():
                r = C.parse_x1_text(p)
                XS.convert(r, rel_of(p))
                return r
    return None


def t9_npc_powerups(shared):
    """SPEC 22.7: heroes.convert_npc_powerups over every XML1 NPC style."""
    from xml1build import heroes as H
    print('T9 NPC powerups (heroes.convert_npc_powerups)')
    values = H.Values(C.parse_x1_text(X1_DATA / 'values.xml'))
    heroes = {(s.get('powerstyle') or '').lower() for s in C.parse_x1_text(X1_DATA / 'herostat.eng').iter()
              if s.get('powerstyle')}
    heroes |= {(s.get('powerstyle') or '').lower() for s in C.parse_x1_text(X1_DATA / 'npcstat.eng').iter()
               if (s.get('name') or '').lower() in {n.lower() for n in H.ROSTER_NPC}}
    total, before, left, idem, errs = collections.Counter(), 0, [], True, []
    for p in x1_styles():
        stem = p.stem.lower()
        if stem in heroes or p.name.lower() == 'shared_nodes.eng' or stem == 'moveset_stealth':
            continue
        root = C.parse_x1_text(p)
        if root is None:
            continue
        XS.convert(root, rel_of(p))
        before += sum(1 for f in CE.style_findings(root, shared) if f.kind in ('x1_powerup_form', 'x1_powerup_remove'))
        c, rep = H.convert_npc_powerups(root, values, f'{stem}:')
        total.update(c)
        errs += rep['errors']
        snap = ET.tostring(root)
        again, _ = H.convert_npc_powerups(root, values)
        idem &= not again and ET.tostring(root) == snap
        left += [f.text(stem) for f in CE.style_findings(root, shared)
                 if f.kind in ('x1_powerup_form', 'x1_powerup_remove', 'x1_powerup_update', 'affecter')]
    check(before > 0 and not left, f'{before} XML1 powerup forms before; after: none left, every affecter registered '
                                   f'{left[:3]}')
    check(dict(total) == EXPECTED_NPC_CHANGES, f'changes {dict(sorted(total.items()))}')
    check(idem, 'second conversion changes nothing (idempotent)')
    check(not errs, f'every value code resolved {errs[:3]}')

    def move(r, name):
        return next(m for m in r.iter('FightMove') if (m.get('name') or '').lower() == name)

    def pu(m, tag=None):
        return next(t for t in m.iter('trigger') if t.get('name') == 'powerup' and (tag is None or t.get('tag') == tag))

    def conv(stem):
        r = _x1_npc_style(stem)
        H.convert_npc_powerups(r, values)
        return r
    blob = conv('ps_blob')
    on, off = pu(move(blob, 'armor_on')), move(blob, 'armor_off').find('trigger')
    aff = [a.attrib for a in on.iter('affecter')]
    check(aff == [{'attribute': 'def_damage', 'level': '0', 'affect_type': 'scale'}] and on.get('tag_name') ==
          'def_damage' and on.get('powerup') is None, f'Blob armor_on: {on.attrib} {aff}')
    check(off.attrib == {'tag': '1', 'remove_tag': 'def_damage'}, f'Blob armor_off tag update: {off.attrib}')
    fo = pu(move(conv('ps_shadowdemon'), 'fly_out'))
    check(fo.attrib == {'name': 'powerup', 'time': '0', 'remove_tag': 'invisible'} and not len(fo),
          f"shadowdemon fly_out = XML2 retail's remove form: {fo.attrib}")
    inv = next(t for t in move(conv('ps_grsoelite'), 'power_boost').iter('trigger') if t.get('class') == 'invisible')
    check(inv.get('no_think') == 'true' and inv.get('no_hurt') is None and
          [a.get('attribute') for a in inv.iter('affecter')] == ['invisible'] and
          not [k for k in inv.attrib if k.startswith('func_')], f'grsoelite cloak -> class invisible: {inv.attrib}')
    td = pu(move(conv('ps_mastermold_one'), 'shockshield_on'), '2')
    check(td.get('class') == 'touch_damage' and td.get('damage') == '15 25' and td.get('level') is None,
          f'Master Mold shock shield -> touch_damage rand(L3, L4) = 15..25: {td.attrib}')
    a1 = pu(move(conv('ps_juggernaut'), 'armor1'))
    check([a.attrib for a in a1.iter('affecter')] == [{'attribute': 'def_damage', 'level': '20'}] and
          a1.get('powerusage') == '20' and a1.get('tag_name') == 'def_damage' and
          [f.get('how_used') for f in a1.iter('special_fx')] == ['primary', 'deactivation'],
          f'Juggernaut armor1: A6 -> 20, powerusage P2 -> 20 (SPEC 24), expire fx at deactivation: {a1.attrib}')
    jug = conv('ps_juggernaut')
    pb = [(t.attrib, [x.attrib for x in t.iter('affecter')]) for t in move(jug, 'power_boost') if t.tag == 'trigger'
          and t.get('tag')]
    st = [(t.get('tag'), t.get('time'), t.get('life'), [x.attrib for x in t.iter('affecter')])
          for t in move(jug, 'armor_start') if t.tag == 'trigger' and t.get('tag')]
    end = [t.attrib for t in move(jug, 'armor_end') if t.tag == 'trigger' and t.get('tag')]
    check(pb[0][0] == {'tag': '1', 'time': '-1'} and pb[1][0].get('tag') == '100' and
          pb[1][1] == [{'attribute': 'def_damage', 'level': '50'}] and
          st == [('100', '-1', None, []), ('101', '0.69', '60', [{'attribute': 'def_damage', 'level': '0',
                                                                    'affect_type': 'scale'}])] and
          end == [{'tag': '100', 'remove_tag': 'def_damage'}],
          f'Juggernaut power_boost A6 -> A8 (tag 1 off, tag 100 level 50), armor_start 60 s scale 0 (tag 101), '
          f'armor_end removes tag 100: {pb} {st} {end}')
    hv = pu(move(conv('ps_havok'), 'knockback_powerup'))
    check([a.attrib for a in hv.iter('affecter')] == [{'attribute': 'atk_knockback', 'level': '430',
                                                       'affect_type': 'sum', 'scope_node': 'cyclops_optic'}],
          f'Havok: K7 -> 430 and scope_node on the affecter: {[a.attrib for a in hv.iter("affecter")]}')
    # the heroes' converter: the special_fx XMen2.exe itself makes of those XML1 attributes (0x53f14c..0x53f24c)
    t = ET.fromstring('<trigger name="powerup" powerup="move" level="0" affect_type="scale" effect="a" fx_bolt="B" '
                      'effect_cust1="c1" effect_cust2="c2" func_activate="frozenactivate"/>')
    H.convert_powerup_trigger(t, 't', {})
    fx = [(f.get('effect'), f.get('how_used'), f.get('tag'), f.get('bolt')) for f in t.iter('special_fx')]
    check(fx == [('a', 'primary', None, 'B'), ('c1', 'custom', '1', None), ('c2', 'custom', '2', None)],
          f'effect / fx_bolt / effect_cust1 / effect_cust2 -> {fx}')
    t = ET.fromstring('<trigger name="powerup" powerup="def_damage" level="1" effect_cust1="x" '
                      'func_deactivate="customeffect1deactivate"/>')
    H.convert_powerup_trigger(t, 't', {})
    check([f.get('how_used') for f in t.iter('special_fx')] == ['deactivation'],
          'customeffect1deactivate -> how_used="deactivation" (0x6de16c; "deactivate" parses as custom)')


def _indent(el):
    e = copy.deepcopy(el)
    ET.indent(e, '    ')
    return '    ' + ET.tostring(e, encoding='unicode')


class _ReadOnlyValidator:
    """the part of validate.Validator V18 uses, over an existing build (its registry.json), without a ctx."""

    def __init__(self, out, base):
        self.ctx = type('Ctx', (), {'base': base, 'out': out})()
        self.idx = C.FileIndex(out, exclude_top=C.META_NAMES)
        reg = json.loads((out / '_build' / 'registry.json').read_text(encoding='utf-8'))
        self.reg = {C.norm(k): e for k, e in reg.get('entries', {}).items()}

    def entry(self, rel):
        return self.reg.get(C.norm(rel))

    def tree(self, rel):
        p = self.idx.path(rel)
        return xmlb.decode(p.read_bytes()) if p is not None else None


if __name__ == '__main__':
    sys.exit(main())
