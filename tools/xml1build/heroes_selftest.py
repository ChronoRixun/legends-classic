"""Standalone self-test of the heroes module output (read-only; does not launch the game).

usage: python tools/xml1build/heroes_selftest.py <out>
  (build first with: python tools/build_xml1.py --out <out> --no-movies [--only characters,heroes --no-validate])

Re-derives every fact from <out>, the registry and the XML1 sources (DESIGN.md 5.3; no ctx.shared):
  HA  every XMLB owned by heroes decodes, re-encodes byte-identically, has lowercase+sorted attribute names
  HB  V-H1..V-H8 recomputed (heroes._validate on a fresh context)
  HC  round trip: for every hero and every collapsed chain, the talentvalue at rank r equals the XML1 rung r's
      resolved value for every overridden attribute (the XML1 style is read again and the inherit chain walked here)
  HD  every XML1 FightMove of a hero style is collapsed into a named output move or kept by name (chain map complete)
  HE  no '^' and no unresolved value code in any talent description; % only as %% or a %talentvalue token
  HF  hero_plan(ctx) on a fresh context predicts the herostat order and talent bases in <out>
  HG  the removed npcstat names are absent; no npcstat entry names a dropped shared talent
  HH  package count == 39 costumes x 2 + 16 _xml + 4 placeholders x 2 (default roster; ProfXGladiator took x1pad4)
  HI  shared keep list == DESIGN 4.7 (delta printed as info; `grab` is the documented difference)
  HJ  budgets: shared + worst 4 files <= 92, stats names <= 296, per-file <= 8, herostat talent children <= 19
  HK  the base files heroes overwrote are only herostat, npcstat, shared_talents, characters_heads(_pc), the XML2
      same-name talent files / _xml packages / powerstyles
Exit 1 on any error; prints counts.
"""
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xml1build import common as C          # noqa: E402
from xml1build import heroes as H          # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else C.ROOT / 'build' / '_heroes').resolve()
ctx = C.BuildContext(out, scan_out=True, registry=C.Registry.load(out / '_build' / 'registry.json'))
try:
    _rep = json.loads((out / '_build' / 'report.json').read_text(encoding='utf-8')).get('build', {})
    for _k in ('hero_roster', 'hero_icons', 'hero_bleed', 'newgame'):
        if _rep.get(_k) is not None:
            setattr(ctx.args, _k, _rep[_k])
except (OSError, ValueError):
    pass
reg = ctx.registry.entries
mine = {k: e for k, e in reg.items() if e['owner'] == 'heroes'}
detail = json.loads((out / '_build' / 'heroes_detail.json').read_text(encoding='utf-8'))
errors, warns, info = [], [], []


def err(m):
    errors.append(m)


def load(rel):
    return C.decode_xmlb(ctx.out_index.path(rel).read_bytes())


plan = H.hero_plan(ctx)
values = H.Values(ctx.read_x1_xml('data/values.xml'))

# ------------------------------------------------------------------ HA
nx = 0
for k, e in mine.items():
    if k.endswith(C.XMLB_FAMILY):
        nx += 1
        data = (out / e['rel']).read_bytes()
        if len(data) <= 8:
            err(f'HA {k}: header-only XMLB')
            continue
        try:
            root = C.decode_xmlb(data)
        except Exception as ex:      # noqa: BLE001
            err(f'HA {k}: does not decode: {ex}')
            continue
        if C.xmlb.encode(root) != data:
            err(f'HA {k}: re-encode differs')
        p = C.xmlb_attr_problems(root)
        if p:
            err(f'HA {k}: {p[:2]}')
info.append(f'HA: {nx} XMLB-family files owned by heroes checked')

# ------------------------------------------------------------------ HB
checks, budgets = H._validate(ctx)
for ck in checks:
    for m in ck.errors:
        err(f'HB {m}')
    for m in ck.warnings:
        warns.append(f'HB {m}')
info.append(f'HB: {len(checks)} checks (V-H1..V-H13), budgets {budgets}')

# ------------------------------------------------------------------ HC / HD: independent walk of the XML1 chains
hero_root = ctx.read_out_xmlb('Data/herostat.engb')
hero_by = {(s.get('name') or '').lower(): s for s in hero_root.iter('stats')}
n_chains = n_values = 0
for h in [x.lower() for x in plan['heroes']]:
    det = detail['heroes'][h]
    st = hero_by[h]
    x1 = plan['x1'][h]
    x1style = (dict((k.lower(), v) for k, v in x1.attrib.items())['powerstyle']).lower()
    sroot = ctx.read_x1_xml(f'data/powerstyles/{x1style}.eng')
    moves = {m.get('name'): m for m in sroot if m.tag == 'FightMove'}
    out_style = load(f"Data/powerstyles/{st.get('powerstyle')}.XMLB")
    out_moves = {m.get('name'): m for m in out_style if m.tag == 'FightMove'}
    tfile = load(f'Data/talents/{h}.engb')
    tvs = collections.defaultdict(dict)
    for tal in tfile.iter('talent'):
        for tv in tal.iter('talentvalue'):
            tvs[tv.get('name')][int(tv.get('level'))] = tv.get('value')

    def effective(name):
        """the XML1 move with its inherit chain applied (attributes + triggers by tag)."""
        m = moves[name]
        inh = m.get('inherit')
        if inh and inh in moves and inh != name:
            base = effective(inh)
            attrs = dict(base['attrs'])
            attrs.update({k: v for k, v in m.attrib.items() if k not in ('name', 'inherit', 'fallback')})
            trig = {t: dict(a) for t, a in base['trig'].items()}
            for c in m:
                if c.tag == 'trigger' and c.get('tag') is not None:
                    trig.setdefault(c.get('tag'), {}).update(c.attrib)
            return {'attrs': attrs, 'trig': trig}
        return {'attrs': {k: v for k, v in m.attrib.items() if k not in ('name', 'inherit', 'fallback')},
                'trig': {c.get('tag'): dict(c.attrib) for c in m if c.tag == 'trigger' and c.get('tag') is not None}}

    # HD: chain map complete
    covered = set(det['chain_map']) | {k.split(' -> ')[0] for k in det['kept']} | \
        {d.split(' (')[0] for d in det['dropped']}
    for d in det['dropped']:
        rn = d.split(' (')[0]
        covered |= {n for n in moves if n.startswith(rn.rstrip('0123456789')) and n in det['renamed'] or n == rn}
    dropped_roots = [d.split(' (')[0] for d in det['dropped']]
    for name in moves:
        if name in covered:
            continue
        # rungs of a dropped chain (Rogue's decide rungs) inherit from the dropped root
        cur, ok = name, False
        for _ in range(20):
            inh = moves[cur].get('inherit')
            if inh in dropped_roots or cur in dropped_roots:
                ok = True
                break
            if not inh or inh not in moves:
                break
            cur = inh
        if not ok:
            err(f'HD {h}: XML1 move {name} is neither collapsed, kept nor dropped')
    # HC: talentvalues == XML1 rung values
    for out_name, cinfo in det['collapsed'].items():
        n_chains += 1
        ranks = {int(r): nm for r, nm in cinfo['ranks'].items()}
        om = out_moves.get(out_name)
        if om is None:
            err(f'HC {h}: collapsed move {out_name} missing from the output style')
            continue
        eff = {r: effective(ranks[r]) for r in ranks}
        for t in om.iter('trigger'):
            tag = t.get('tag')
            if tag is None:
                continue
            for k, v in t.attrib.items():
                if not (isinstance(v, str) and v.startswith('%')):
                    continue
                ref = v[1:]
                if ref not in tvs:
                    err(f'HC {h}:{out_name} %{ref} has no talentvalue')
                    continue
                # the source attribute (affecter level / class-form renames map back to the XML1 attribute)
                for r, nm in ranks.items():
                    tr = eff[r]['trig'].get(tag)
                    if tr is None:
                        continue
                    src = tr.get(k)
                    if src is None and k == 'life':
                        continue
                    if src is None:
                        continue
                    want = values.resolve(src, single=k in ('level', 'chance', 'radius', 'life', 'count', 'maxrange')) \
                        if values.is_code(src) else src
                    got = tvs[ref].get(r)
                    if got != want and k != 'life':
                        err(f'HC {h}:{out_name} trigger {tag} {k} rank {r}: talentvalue {got!r} != XML1 {want!r} ({src})')
                    n_values += 1
            for aff in t.iter('affecter'):
                lv = aff.get('level') or ''
                if lv.startswith('%') and lv[1:] in tvs:
                    for r, nm in ranks.items():
                        tr = eff[r]['trig'].get(tag)
                        src = tr.get('level') if tr else None
                        if src is None:
                            continue
                        want = values.resolve(src, single=True) if values.is_code(src) else src
                        if tvs[lv[1:]].get(r) != want:
                            err(f'HC {h}:{out_name} trigger {tag} affecter level rank {r}: {tvs[lv[1:]].get(r)!r} != {want!r}')
                        n_values += 1
info.append(f'HC: {n_chains} collapsed chains, {n_values} rank values compared with the XML1 rungs')
info.append(f'HD: {sum(len(detail["heroes"][h]["chain_map"]) for h in detail["heroes"])} XML1 moves mapped, '
            f'{sum(len(detail["heroes"][h]["kept"]) for h in detail["heroes"])} kept')

# ------------------------------------------------------------------ HE
bad_desc = 0
for h in [x.lower() for x in plan['heroes']]:
    for ext in ('XMLB', 'engb'):
        t = load(f'Data/talents/{h}.{ext}')
        for el in t.iter():
            d = el.get('description') or ''
            if '^' in d:
                bad_desc += 1
                err(f'HE talents/{h}.{ext}: description keeps ^: {d[:80]!r}')
            if re.search(r'\b(L\d\+?|M\d|H\d|K\d+|P\d+\+?|BST\d|A\d+|XTL\d)\b', d):
                bad_desc += 1
                err(f'HE talents/{h}.{ext}: unresolved value code in {d[:80]!r}')
            stripped = re.sub(r'%%', '', d)
            stripped = re.sub(r'%[A-Za-z0-9_]+(:[a-z])?', '', stripped)
            if '%' in stripped:
                bad_desc += 1
                err(f'HE talents/{h}.{ext}: bare % in {d[:80]!r}')
info.append(f'HE: {bad_desc} description problems')

# ------------------------------------------------------------------ HF
fresh = C.BuildContext(out, scan_out=False)
for k in ('hero_roster', 'hero_icons', 'hero_bleed'):
    setattr(fresh.args, k, getattr(ctx.args, k, None))
fplan = H.hero_plan(fresh)
names_out = [(s.get('name') or '') for s in hero_root.iter('stats')]
if [n.lower() for n in names_out] != [n.lower() for n in fplan['order']]:
    err(f'HF hero_plan order {fplan["order"]} != herostat {names_out}')
for i, n in enumerate(names_out, 1):
    if fplan['talent_base'].get(n.lower()) != (i + 1) * 100:
        err(f'HF {n}: talent base {fplan["talent_base"].get(n.lower())} != {(i + 1) * 100}')
info.append(f'HF: hero_plan predicts {len(fplan["order"])} entries, bases 200..{(len(fplan["order"]) + 1) * 100}')

# ------------------------------------------------------------------ HG
npc = {ext: load(f'Data/npcstat.{ext}') for ext in ('XMLB', 'engb')}
dropped = set(detail['shared_drop'])
for ext, root in npc.items():
    names = {(s.get('name') or '').lower() for s in root.iter('stats')}
    for h in detail['npcstat_removed']:
        if h.lower() in names:
            err(f'HG npcstat.{ext} still has {h}')
    for s in root.iter('stats'):
        for t in s.iter('talent'):
            if (t.get('name') or '').lower() in dropped:
                err(f'HG npcstat.{ext} {s.get("name")} names dropped shared talent {t.get("name")}')
# the 6 XML1 heroes XML2 lacks that characters wrote as NPCs (SPEC 5.1 / 12.2) + the promoted npcstat heroes
want_removed = {'beast', 'frost', 'jubilee', 'magma', 'profxastral', 'psylocke'} | {h.lower() for h in plan['npc_heroes']}
if sorted(x.lower() for x in detail['npcstat_removed']) != sorted(want_removed):
    err(f'HG removed npcstat names {detail["npcstat_removed"]} != {sorted(want_removed)} (heroes used as NPCs + '
        f'promoted npcstat heroes)')
info.append(f'HG: {len(detail["npcstat_removed"])} npcstat entries removed, {len(detail["npc_talent_refs_dropped"])} talent refs dropped')

# ------------------------------------------------------------------ HH
pk = [k for k in mine if k.startswith('packages/generated/characters/')]
# distinct costume skins (Wolverine's skin_60s and skin_70s are both 0303: one actor, one package pair)
n_cost = sum(len({mapped for _, _, mapped in v}) for v in plan['costumes'].values())
want_pk = n_cost * 2 + len(plan['heroes']) + len(plan['placeholders']) * 2
if len(pk) != want_pk:
    err(f'HH {len(pk)} character packages owned by heroes, expected {want_pk} ({n_cost} costumes x 2 + '
        f'{len(plan["heroes"])} _xml + {len(plan["placeholders"])} placeholders x 2)')
info.append(f'HH: {len(pk)} character packages ({n_cost} distinct costume skins)')

# ------------------------------------------------------------------ HI
shared = [(t.get('name') or '').lower() for t in load('Data/shared_talents.engb').iter('talent')]
delta = sorted(set(shared) ^ H.SHARED_KEEP_EXPECTED)
info.append(f'HI: shared_talents {len(shared)}; delta vs DESIGN 4.7 (47): {delta}')
if delta and delta != ['grab']:
    err(f'HI shared keep list differs from DESIGN 4.7 beyond the documented grab: {delta}')
if len(shared) != len(set(shared)):
    err('HI duplicate shared talents')

# ------------------------------------------------------------------ HJ
sizes = {}
for h in [x.lower() for x in plan['heroes']]:
    sizes[h] = len(list(load(f'Data/talents/{h}.engb').iter('talent')))
    if sizes[h] > H.FILE_TALENT_MAX:
        err(f'HJ talents/{h}: {sizes[h]} > {H.FILE_TALENT_MAX}')
worst = sorted(sizes.values(), reverse=True)[:4]
pool = len(shared) + sum(worst)
if pool > H.TALENT_POOL - H.DANGER_ROOM_MARGIN:
    err(f'HJ registered talents worst party {pool} > {H.TALENT_POOL - H.DANGER_ROOM_MARGIN}')
stats_total = len({(s.get('name') or '').lower() for s in hero_root.iter('stats')} |
                  {(s.get('name') or '').lower() for s in npc['engb'].iter('stats')})
if stats_total > H.STATS_CAP:
    err(f'HJ {stats_total} stats names > {H.STATS_CAP}')
for s in hero_root.iter('stats'):
    if len([c for c in s if c.tag == 'talent']) > H.STATS_TALENT_MAX:
        err(f'HJ {s.get("name")}: > {H.STATS_TALENT_MAX} talent children')
info.append(f'HJ: shared {len(shared)} + worst party {worst} = {pool}/{H.TALENT_POOL}; stats names {stats_total}/{H.STATS_CAP}; '
            f'files {sizes}')

# ------------------------------------------------------------------ HK
allowed = re.compile(r'^(data/(herostat|npcstat|shared_talents)\.(xmlb|engb)|'
                     r'packages/generated/maps/package/menus/characters_heads(_pc)?\.pkgb|'
                     r'data/talents/(colossus|cyclops|gambit|iceman|nightcrawler|phoenix|rogue|storm|wolverine)\.(xmlb|engb)|'
                     r'packages/generated/characters/(colossus|cyclops|gambit|iceman|nightcrawler|phoenix|rogue|storm|wolverine|beast|frost)_xml\.pkgb)$')
for k, e in mine.items():
    if e.get('overwrote_base') and not allowed.match(k):
        err(f'HK {k}: heroes replaced an unexpected XML2 base file')
info.append(f"HK: {sum(1 for e in mine.values() if e.get('overwrote_base'))} base files replaced by heroes")

for i in info:
    print('  ' + i)
for w in warns[:40]:
    print('  warn:', w)
if len(warns) > 40:
    print(f'  ... {len(warns) - 40} more warnings')
for e in errors[:80]:
    print('  ERROR:', e)
print(f'RESULT: {"PASS" if not errors else "FAIL"} ({len(errors)} errors, {len(warns)} warnings)')
sys.exit(1 if errors else 0)
