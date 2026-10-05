"""Standalone self-test of the characters module output (does not launch the game, writes nothing to <out>).

usage: python tools/xml1build/characters_selftest.py <out>
  (build first with: python tools/build_xml1.py --out <out> --no-movies --only characters --no-validate)

Re-derives every fact from the <out> tree, the registry and the XML1 sources (it does not trust ctx.shared):
  A  every XMLB-family file owned by characters decodes, re-encodes byte-identically, has lowercase+sorted
     attribute names and is > 8 bytes
  B  stats tables: herostat == 21, unique names <= 296, no dup / no npcstat name in herostat, names <= 31,
     skins 4-5 digits with prefix <= 255, XMLB/engb same name set, shared_talents <= 99 (both files)
  C  per XML1-origin stats entry: skin actor, costume actors, characteranims, powerstyle, moveset1, talents,
     sounddir bank (sound plan), BoltOn models/anims, both own-skin packages
  D  every PKGB owned by characters: every entry resolves (common.package_entry_files) in <out>
  E  renamed IGBs: same size as the XML1 source, no bare old '<id>'/'<id>_outline'/'<id>_skel' names left,
     new names present where old ones were, only string bytes changed
  F  base files replaced only where intended (npcstat, shared_talents, values, leftover style packages)
  G  zone consumers: every XML1 zone .chr name is a stats name; every zone-bundle actorskin/actoranimdb/HUD/UI/
     fightstyle/loading entry (map_package_entry) resolves; every (character, monster_skin) of a zone has
     its mapped actor and package; zone 'loading' numeric textures exist
  H  completeness: every XML1 character-namespace source file has its mapped output (or is XML2-shared / empty)
  I  every asset a written style / imported data/entities file names (effects, models, skins, spawned
     characters, entity classes, icon textures) exists in <out>, or is an XML1 permanent-package file (zones), or
     is dead on the XML1 disc (warning)
  J  SPEC 4.4 XML1-wins prefixes (data/entities, conversations, dialogs, subtitles, motionpaths) imported for
     character bundles: the <out> file comes from the XML1 source, is map_tree_refs-clean (idempotent), and is
     listed by the packages that need it
  K  the pure provider characters.planned_stats(ctx) on a fresh context (no run) predicts exactly the stats
     names in <out> (herostat + npcstat), the heroes used as NPCs and the kept XML2 entries. With the heroes
     module (it owns herostat) npcstat also holds its SPEC 18.1 speaker-only entries
     (scripts_transform.speaker_stats_entries: <hero>_x1double for the renamed NPC doubles that speak, and the
     NPC names of NPC_SPEAKER_CONVERSATIONS - cyclops_scripted, alison, alison_scripted, emma): each must be
     there, with team none and not playable, and they are neither planned XML1 names nor kept XML2 entries
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xml1build import common as C  # noqa: E402
from xml1build.lib import x1names as N  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else C.ROOT / 'build' / '_selftest_characters')
ctx = C.BuildContext(out, scan_out=True)
reg = json.loads((out / '_build' / 'registry.json').read_text(encoding='utf-8'))['entries']
mine = {k: e for k, e in reg.items() if e['owner'] == 'characters'}
detail = json.loads((out / '_build' / 'characters_detail.json').read_text(encoding='utf-8'))
errors, warns, info = [], [], []


def err(m):
    errors.append(m)


def exists(rel):
    r = C.norm(rel)
    return r in ctx.out_index and (r in reg or r in ctx.base_index)


def pkg_ok(kind, fn):
    c = C.package_entry_files(kind, fn)
    return c is None or any(exists(x) for x in c)


def load(rel):
    return C.decode_xmlb(ctx.out_index.path(rel).read_bytes())


# ------------------------------------------------------------------ A
nx = 0
for k, e in mine.items():
    if k.endswith(C.XMLB_FAMILY):
        nx += 1
        data = (out / e['rel']).read_bytes()
        if len(data) <= 8:
            err(f'A {k}: header-only XMLB')
            continue
        try:
            root = C.decode_xmlb(data)
        except Exception as ex:  # noqa: BLE001
            err(f'A {k}: does not decode: {ex}')
            continue
        if C.xmlb.encode(root) != data:
            err(f'A {k}: re-encode differs')
        p = C.xmlb_attr_problems(root)
        if p:
            err(f'A {k}: {p[:2]}')
        if (out / e['rel']).stat().st_size != e['size']:
            err(f'A {k}: size differs from registry')
info.append(f'A: {nx} XMLB-family files checked')

# ------------------------------------------------------------------ B
tabs = {}
for f in ('herostat', 'npcstat'):
    for ext in ('XMLB', 'engb'):
        tabs[(f, ext)] = list(load(f'Data/{f}.{ext}').iter('stats'))
for ext in ('XMLB', 'engb'):
    hn = [s.get('name').lower() for s in tabs[('herostat', ext)]]
    nn = [s.get('name').lower() for s in tabs[('npcstat', ext)]]
    if len(hn) != 21:
        err(f'B herostat.{ext} has {len(hn)} entries')
    if len(set(nn)) != len(nn):
        err(f'B npcstat.{ext} duplicates')
    if set(hn) & set(nn):
        err(f'B npcstat.{ext} names in herostat: {set(hn) & set(nn)}')
    u = set(hn) | set(nn)
    if len(u) > 296:
        err(f'B {ext}: {len(u)} names > 296')
    info.append(f'B {ext}: {len(u)} unique stats names ({len(hn)} heroes + {len(nn)} npcs)')
    for s in tabs[('herostat', ext)] + tabs[('npcstat', ext)]:
        n = s.get('name')
        if len(n) > 31:
            err(f'B name too long {n}')
        for a in ('skin', 'leaderskin', 'mutantskin'):
            v = s.get(a)
            if v is not None and (not re.fullmatch(r'\d{4,5}', v) or int(v[:-2]) > 255):
                err(f'B {n}: {a}={v}')
if {s.get('name').lower() for s in tabs[('npcstat', 'XMLB')]} != {s.get('name').lower() for s in tabs[('npcstat', 'engb')]}:
    err('B npcstat XMLB/engb name sets differ')
tal = {}
for ext in ('XMLB', 'engb'):
    t = [x.get('name').lower() for x in load(f'Data/shared_talents.{ext}').iter('talent')]
    if len(t) > 99:
        err(f'B shared_talents.{ext}: {len(t)} > 99')
    if len(set(t)) != len(t):
        err(f'B shared_talents.{ext}: duplicate talent names')
    tal[ext] = set(t)
if tal['XMLB'] != tal['engb']:
    err('B shared_talents XMLB/engb differ')
info.append(f"B shared_talents: {len(tal['engb'])}")
hero_tal = set()
for a in ctx.out_index.under('data/talents/'):
    if a.lower().endswith('.xmlb'):
        hero_tal |= {t.get('name').lower() for t in load(a).iter('talent')}

# ------------------------------------------------------------------ C
CH_SLOTS = {'ebolton_clawright', 'ebolton_clawleft', 'ebolton_weapon', 'ebolton_altweapon', 'ebolton_cape',
            'ebolton_tail', 'ebolton_wings', 'ebolton_tongue', 'ebolton_autoanim', 'ebolton_autoanim2'}
x1n = {s.get('name').lower() for s in C.parse_x1_text(ctx.x1_path('data/npcstat.eng')) if s.tag.lower() == 'stats'}
x1_origin = x1n | {h.lower() for h in detail['heroes_as_npc']}
checked = 0
for ext in ('XMLB', 'engb'):
    for s in tabs[('npcstat', ext)]:
        n = s.get('name')
        ln = n.lower()
        is_x1 = ln in x1_origin
        bad = err if is_x1 else warns.append
        where = f'C {ext} {n}'
        checked += is_x1
        skin = s.get('skin')
        if skin and not exists(f'actors/{skin}.igb') and not (ln == 'computer' and skin == '21501'):
            bad(f'{where}: actors/{skin}.igb missing')
        for a, v in s.attrib.items():
            if a.startswith('skin_') and skin and not exists(f'actors/{skin[:-2]}{v.zfill(2)}.igb'):
                bad(f'{where}: costume {a} -> actors/{skin[:-2]}{v.zfill(2)}.igb missing')
        ca = s.get('characteranims')
        if ca and not exists(f'actors/{ca}.igb'):
            bad(f'{where}: characteranims {ca} missing')
        ps = s.get('powerstyle')
        if ps and not (exists(f'data/powerstyles/{ps}.xmlb') or exists(f'data/powerstyles/{ps}.engb')):
            bad(f'{where}: powerstyle {ps} missing')
        ms = s.get('moveset1')
        if ms and not exists(f'data/fightstyles/{ms}.xmlb'):
            bad(f'{where}: moveset1 {ms} missing')
        sd = s.get('sounddir')
        if sd and ctx.sound_bank_rel(sd) is None:
            bad(f'{where}: sounddir {sd} has no planned bank')
        for c in s:
            if c.tag == 'talent':
                tn = c.get('name').lower()
                if tn not in tal['engb'] and tn not in hero_tal:
                    bad(f'{where}: talent {tn} undefined')
                if N.is_fightstyle_name(tn) and not exists(f'data/fightstyles/{tn}.xmlb'):
                    bad(f'{where}: fightstyle file {tn} missing')
            elif c.tag == 'BoltOn':
                m = c.get('model', '')
                ok = exists(f'actors/{m}.igb') if N.is_skin_id(m) else exists(m + '.igb')
                if not ok:
                    bad(f'{where}: BoltOn model {m} missing')
                # XMen2.exe 0x44a820 loop: onlyprecache="true" skips; otherwise slot must be in 0x6d6530
                if (c.get('onlyprecache') or '').lower() != 'true' and \
                        (c.get('slot') or '').lower() not in CH_SLOTS:
                    bad(f'{where}: BoltOn {m} slot {c.get("slot")!r} not in the XMen2.exe slot table (dropped)')
                if c.get('anim') and not exists(f"actors/{c.get('anim')}.igb"):
                    bad(f"{where}: BoltOn anim {c.get('anim')} missing")
            elif c.tag not in ('Race', 'Multipart', 'FlyEffect'):
                bad(f'{where}: unexpected child <{c.tag}>')
        if is_x1:
            for nc in ('', '_nc'):
                pk = f'packages/generated/characters/{ln}_{skin}{nc}.pkgb'
                if pk not in mine:
                    err(f'{where}: own package {pk} not written')
            for a in ('leader', 'ratingmelee', 'throwally', 'weapon'):
                if s.get(a) is not None:
                    err(f'{where}: XML1-only attribute {a} left')
info.append(f'C: {checked} XML1-origin entries checked (XMLB+engb)')

# ------------------------------------------------------------------ D
npk = nent = 0
for k, e in mine.items():
    if not k.endswith('.pkgb'):
        continue
    npk += 1
    root = load(e['rel'])
    if len(root) == 0:
        err(f'D {k}: empty package')
    seen = set()
    for el in root:
        nent += 1
        fn = el.get('filename')
        if (el.tag, fn) in seen:
            err(f'D {k}: duplicate entry {el.tag} {fn}')
        seen.add((el.tag, fn))
        if not pkg_ok(el.tag, fn):
            err(f'D {k}: <{el.tag} filename="{fn}"> does not resolve')
        if el.tag in ('actorskin', 'actoranimdb') and (fn.startswith('actors/') or fn != fn.lower()):
            warns.append(f'D {k}: {el.tag} {fn} not a bare lowercase stem')
    if '/characters/' in k:
        if not any(el.tag == 'actorskin' for el in root) and \
                not k.startswith('packages/generated/characters/computer_') and not k.endswith('_xml.pkgb'):
            err(f'D {k}: character package without actorskin')
info.append(f'D: {npk} packages, {nent} entries resolved')
for ln in sorted(x1_origin):
    # the heroes module (SPEC_heroes.md) rewrites the 6 hero-as-NPC packages under its own ownership
    if f'packages/generated/characters/{ln}_xml.fb' in ctx.manifest and \
            f'packages/generated/characters/{ln}_xml.pkgb' not in mine and \
            reg.get(f'packages/generated/characters/{ln}_xml.pkgb', {}).get('owner') != 'heroes':
        err(f'D {ln}_xml: XML1 bundle exists but package not written')

# ------------------------------------------------------------------ E
nren = 0
for k, e in mine.items():
    m = re.fullmatch(r'(actors/|hud/hud_head_|ui/hud/characters/|ui/models/characters/)(\d{5})\.igb', k)
    if not m:
        continue
    new = m.group(2)
    old = str(int(new) - N.SKIN_OFFSET).zfill(4)
    src = ctx.x1_path(f'{m.group(1)}{old}.igb')
    if src is None:
        err(f'E {k}: no XML1 source')
        continue
    a, b = src.read_bytes(), (out / e['rel']).read_bytes()
    if len(a) != len(b):
        err(f'E {k}: size differs from XML1 source')
    olds = [mm.start() for mm in re.finditer(re.escape(old.encode()) + rb'(?:_outline|_skel)?\x00', b)
            if mm.start() >= 4 and b[mm.start() - 4:mm.start()] != b'\x00\x00\x00\x00'
            and int.from_bytes(b[mm.start() - 4:mm.start()], 'little') in range(len(old) + 1, len(old) + 16)]
    if olds:
        err(f'E {k}: {len(olds)} length-prefixed "{old}" names left')
    had = len(re.findall(re.escape(old.encode()) + rb'(?:_outline|_skel)?\x00', a))
    has = len(re.findall(re.escape(new.encode()) + rb'(?:_outline|_skel)?\x00', b))
    if had and not has:
        err(f'E {k}: {had} old names but no new ones')
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    # every changed byte must lie inside a string that now reads <new>[_outline|_skel]
    for i in diff[:2000]:
        win = b[max(0, i - 16):i + 16]
        if new.encode() not in win:
            err(f'E {k}: byte {i:#x} changed outside a renamed name')
            break
    nren += 1
info.append(f'E: {nren} renamed IGBs checked')

# ------------------------------------------------------------------ F
intended = {'data/npcstat.xmlb', 'data/npcstat.engb', 'data/shared_talents.xmlb', 'data/shared_talents.engb',
            'data/values.xmlb', 'data/boltonactoranims.xmlb'}
# the replaced tables must keep every XML2 entry except npcstat's dropped ones (append-only merges)
for rel, tag in (('Data/values.XMLB', 'value'), ('Data/boltonactoranims.XMLB', 'actor_skin'),
                 ('Data/shared_talents.XMLB', 'talent'), ('Data/shared_talents.engb', 'talent')):
    if C.norm(rel) in mine:
        old = [C.xmlb.to_text(e) for e in C.decode_xmlb(ctx.base_index.path(rel).read_bytes()).iter(tag)]
        new = [C.xmlb.to_text(e) for e in load(rel).iter(tag)]
        if new[:len(old)] != old:
            err(f'F {rel}: XML2 entries changed (merge must be append-only)')
        info.append(f'F {rel}: {len(old)} XML2 + {len(new) - len(old)} appended')
for ext in ('XMLB', 'engb'):
    old = {s.get('name').lower(): C.xmlb.to_text(s) for s in C.decode_xmlb(ctx.base_index.path(f'Data/npcstat.{ext}').read_bytes()).iter('stats')}
    for s in tabs[('npcstat', ext)]:
        n = s.get('name').lower()
        if n in old and n not in x1_origin and C.xmlb.to_text(s) != old[n]:
            err(f'F npcstat.{ext}: kept XML2 entry {n} modified')
for k, e in mine.items():
    xml_pkg = re.fullmatch(r'packages/generated/characters/(.+)_xml\.pkgb', k)
    style_pkg = k.startswith(('packages/generated/powerstyles/', 'packages/generated/fightstyles/'))
    if e['overwrote_base'] and k not in intended and not style_pkg and not (xml_pkg and xml_pkg.group(1) in x1_origin):
        err(f'F {k}: replaced an XML2 base file')
    if e['overwrote_base'] and k.startswith('packages/generated/'):
        base_root = C.decode_xmlb(ctx.base_index.path(k).read_bytes())
        for el in base_root:
            fn = el.get('filename')
            if el.tag in ('xml',) and not ctx.base_index.find(fn, ('.xmlb', '.engb')):
                pass            # leftover pointing at a missing style: fine to replace
            else:
                warns.append(f'F {k}: replaced base package had resolvable entry {el.tag} {fn}')
info.append(f"F: {sum(1 for e in mine.values() if e['overwrote_base'])} base files replaced")

# ------------------------------------------------------------------ G
stats_names = {s.get('name').lower() for s in tabs[('herostat', 'engb')] + tabs[('npcstat', 'engb')]}
nchr = 0
for rel in ctx.x1_rels('maps/'):
    if rel.endswith('.chr'):
        r = ctx.read_x1_xml(rel)
        if r is None:
            continue
        for el in r.iter():
            if el.tag.lower() == 'character':
                nchr += 1
                if el.get('name', '').lower() not in stats_names:
                    err(f'G {rel}: character {el.get("name")} not a stats name')
nz = 0
for zone in ctx.x1_zones():
    for path, kind in ctx.zone_bundle(zone):
        k = kind.lower()
        p = C.norm(path)
        if p.endswith(('.fre', '.ger')):
            continue
        if k in ('actorskin', 'actoranimdb') or re.fullmatch(r'(hud/hud_head_|ui/hud/characters/|ui/models/characters/)\d{4}\.igb', p) \
                or (k == 'fightstyle') or re.fullmatch(r'textures/loading/\d{4}\.igb', p):
            kind2, fn = C.map_package_entry(kind, p)
            nz += 1
            if not pkg_ok(kind2, fn):
                src_empty = ctx.x1_is_empty(p) if ctx.x1_path(p) else None
                (warns.append if src_empty or ctx.x1_path(p) is None else err)(
                    f'G zone {zone}: {kind} {path} -> {fn} unresolved (x1 source '
                    f'{"empty" if src_empty else "missing" if src_empty is None else "present"})')
pairs = set()
loads = set()
for rel in ctx.x1_rels('maps/'):
    if not rel.endswith(('.eng', '.xml')):
        continue
    r = ctx.read_x1_xml(rel)
    if r is None:
        continue
    for el in r.iter():
        ch, ms = el.get('character'), el.get('monster_skin')
        if ch and ch.strip().lower() not in stats_names:
            err(f'G {rel}: <{el.tag} character="{ch}"> is not a stats name (spawner would spawn nothing)')
        if ch and ms and re.fullmatch(r'\d{4}', ms):
            pairs.add((ch.lower(), ms, rel))
        for a, v in el.attrib.items():
            if re.fullmatch(r'(?i)textures[/\\]loading[/\\]\d{4}', v.strip()):
                loads.add((C.map_loading_texture(v.strip().replace('\\', '/')), rel))
for ch, ms, rel in sorted(pairs):
    ns = C.map_skin(ms)
    if not exists(f'actors/{ns}.igb') and ms != '7501':
        err(f'G {rel}: monster_skin {ms} -> actors/{ns}.igb missing')
    if ch in stats_names and ch in x1_origin:
        for nc in ('', '_nc'):
            if not exists(f'packages/generated/characters/{ch}_{ns}{nc}.pkgb'):
                err(f'G {rel}: no package {ch}_{ns}{nc} for monster_skin {ms}')
for t, rel in sorted(loads):
    if not exists(t + '.igb'):
        err(f'G {rel}: loading texture {t} missing')
info.append(f'G: {nchr} zone .chr names, {nz} zone bundle character entries, {len(pairs)} monster_skin uses, '
            f'{len(loads)} numeric loading refs checked')

# ------------------------------------------------------------------ H
missing = 0
for rel in ctx.x1_rels('actors/'):
    stem = rel[len('actors/'):-4]
    if not rel.endswith('.igb'):
        continue
    if ctx.x1_is_empty(rel):
        continue
    m = C.map_animdb(stem) if not re.fullmatch(r'\d{4}', stem) else C.map_skin(stem)
    if not exists(f'actors/{m}.igb'):
        err(f'H actors/{stem} -> actors/{m}.igb missing')
        missing += 1
for pre in ('hud/hud_head_', 'ui/hud/characters/', 'ui/models/characters/', 'textures/loading/'):
    for rel in ctx.x1_rels(pre):
        stem = rel[len(pre):-4]
        if re.fullmatch(r'\d{4}', stem) and not exists(f'{pre}{C.map_skin(stem)}.igb'):
            err(f'H {rel} -> {pre}{C.map_skin(stem)} missing')
            missing += 1
for kind in ('powerstyles', 'fightstyles'):
    for rel in ctx.x1_rels(f'data/{kind}/'):
        stem, ext = C.split_ext(rel[len(f'data/{kind}/'):])
        if ext not in ('.eng', '.xml'):
            continue
        m = C.map_powerstyle(stem) if kind == 'powerstyles' else C.map_fightstyle(stem)
        if not exists(f'data/{kind}/{m}.xmlb'):
            err(f'H {rel} -> data/{kind}/{m} missing')
            missing += 1
        if ext == '.eng' and not exists(f'data/{kind}/{m}.engb') and not ctx.base_index.find(f'data/{kind}/{m}', ('.xmlb',)):
            err(f'H {rel}: localized style without engb')
info.append(f'H: namespace completeness, {missing} missing')

# ------------------------------------------------------------------ I
permanent = {C.norm(p) for p, _ in ctx.manifest.get('packages/generated/maps/package/permanent.fb', [])}
x1_ent_defs = {}
for rel in [r for r in ctx.x1_rels('data/entities/') if r.endswith(('.xml', '.eng'))] + \
        ['data/common_ents.xml', 'data/item_ents.xml']:
    r = ctx.read_x1_xml(rel) if ctx.x1_path(rel) else None
    if r is None:
        continue
    for top in C.iter_roots(r):
        for e_ in [top] + list(top):
            if e_.get('name'):
                x1_ent_defs.setdefault(e_.get('name').lower(), set()).add(rel)
out_ent_names = set()
for a in ctx.out_index.under('data/'):
    la = a.lower()
    if la.endswith(('.xmlb', '.engb')) and (la.startswith('data/entities/') or Path(la).stem in ('common_ents', 'item_ents')):
        try:
            r = load(a)
        except Exception:  # noqa: BLE001
            continue
        for top in C.iter_roots(r):
            for e_ in [top] + list(top):
                if e_.get('name'):
                    out_ent_names.add(e_.get('name').lower())
EFF_ATTR = re.compile(r'(?:effect|effect_cust\d|footstepfx)$')
ncheck = 0
dead_refs = set()


def ref_missing(src_rel, what):
    """src_rel (XML1 disc path) is not in <out>: permanent (zones) / dead (warn) / error."""
    if src_rel in permanent:
        return
    if ctx.x1_path(src_rel) is None or ctx.x1_is_empty(src_rel):
        dead_refs.add(f'{what} -> {src_rel}')
        return
    err(f'I {what}: {src_rel} is on the XML1 disc but not in <out>')


stats_names_all = {s.get('name').lower() for s in tabs[('herostat', 'engb')] + tabs[('npcstat', 'engb')]}
for k, e in mine.items():
    is_style = k.startswith(('data/powerstyles/', 'data/fightstyles/')) and k.endswith('.xmlb')
    is_ent = k.startswith('data/entities/') and k.endswith('.xmlb')
    if not (is_style or is_ent):
        continue
    root = load(e['rel'])
    for el in root.iter():
        for a, v in el.attrib.items():
            v = (v or '').strip()
            if not v or v.lower() in ('true', 'false', 'none', '0', '1'):
                continue
            what = f'{k} <{el.tag} {a}="{v}">'
            if EFF_ATTR.search(a) or (is_ent and a in ('loopfx', 'trailfx')):
                ncheck += 1
                n = C.norm(v)
                n = n[:-4] if n.endswith('.xml') else n
                n = n[len('effects/'):] if n.startswith('effects/') else n
                if not (exists(f'effects/{n}.xmlb') or exists(f'effects/{n}.engb')):
                    ref_missing(f'effects/{n}.xml', what)
            elif a in ('model', 'bolton') and not N.is_skin_id(v):
                ncheck += 1
                m = C.norm(v).removesuffix('.igb')
                if is_ent and not m.startswith('models/'):
                    m = 'models/' + m
                if not exists(m + '.igb'):
                    ref_missing(m + '.igb', what)
            elif a in ('skin', 'actorskin') or (a == 'model' and N.is_skin_id(v)):
                ncheck += 1
                if not exists(f'actors/{v}.igb'):
                    err(f'I {what}: actors/{v}.igb missing')
            elif a == 'character':
                ncheck += 1
                if v.lower() not in stats_names_all:
                    err(f'I {what}: not a stats name')
            elif a in ('entity', 'deathspawn', 'xdeathspawn', 'actspawn'):
                ncheck += 1
                if v.lower() not in out_ent_names:
                    defs = x1_ent_defs.get(v.lower())
                    if not defs:
                        dead_refs.add(f'{what} -> entity class {v}')
                    elif not any(C.norm(d) in permanent for d in defs):
                        # a zones-only definition file is fine in a full build; in a characters-only build it is
                        # expected to be missing -> warn, the full-build validator run covers the rest
                        warns.append(f'I {what}: entity class defined in {sorted(defs)} which is not in <out> yet')
            elif a == 'iconfile':
                ncheck += 1
                t = C.split_ext(C.norm(v))[0]
                if not exists(t + '.igb'):
                    ref_missing(t + '.igb', what)
for d in sorted(dead_refs):
    warns.append(f'I dead on the XML1 disc: {d}')
info.append(f'I: {ncheck} style/entity references checked, {len(dead_refs)} dead on the XML1 disc')

# ------------------------------------------------------------------ J
FORCE = ('conversations/', 'dialogs/', 'subtitles/', 'data/entities/', 'motionpaths/')
pkg_lists = {}
for k, e in reg.items():
    if k.endswith('.pkgb') and k.startswith('packages/generated/'):
        try:
            for el in load(e['rel']):
                pkg_lists.setdefault(C.norm(el.get('filename') or ''), set()).add(k)
        except Exception:  # noqa: BLE001
            pass
nj = 0
wanted = set()
for bk, ents in ctx.manifest.items():
    if bk.startswith(('packages/generated/characters/', 'packages/generated/powerstyles/',
                      'packages/generated/fightstyles/')):
        for p, kind in ents:
            n = C.norm(p)
            if n.startswith(FORCE) and not n.endswith(('.fre', '.ger')):
                wanted.add(n)
for n in sorted(wanted):
    stem, ext = C.split_ext(n)
    outs = [x for x in (C.norm(stem + '.xmlb'), C.norm(stem + '.engb'), C.norm(stem + '.igb')) if x in reg]
    if not outs:
        if ctx.x1_path(n) and not ctx.x1_is_empty(n):
            err(f'J {n}: listed by a character/style bundle but not written')
        continue
    for o in outs:
        nj += 1
        if reg[o]['source'] != str(ctx.x1_path(n)):
            err(f'J {o}: source {reg[o]["source"]} is not the XML1 file (XML2 must not win under {FORCE})')
        if o.endswith(('.xmlb', '.engb')):
            r = load(reg[o]['rel'])
            if C.map_tree_refs(r):
                err(f'J {o}: still has unmapped XML1 character references (map_tree_refs changes it)')
    if stem not in pkg_lists:
        warns.append(f'J {stem}: written but listed by no package')
info.append(f'J: {nj} XML1-wins files from character/style bundles checked')

# ------------------------------------------------------------------ K
from xml1build import characters as CH  # noqa: E402
from xml1build import scripts_transform as ST  # noqa: E402
fresh = C.BuildContext(out, scan_out=False)
plan = CH.planned_stats(fresh)
heroes_build = reg.get('data/herostat.engb', {}).get('owner') == 'heroes'
# SPEC 18.1 speaker-only entries the heroes module appends to npcstat (never spawned; not in the characters plan)
speakers = {n.lower() for n in ST.speaker_stats_entries()} if heroes_build else set()
if speakers:
    npc_rows = {s.get('name').lower(): s for s in tabs[('npcstat', 'engb')]}
    for n in sorted(speakers):
        row = npc_rows.get(n)
        if row is None:
            err(f'K SPEC 18.1 speaker entry {n} missing from npcstat')
        elif (row.get('team') or '').lower() != 'none' or (row.get('playable') or '').lower() == 'true':
            err(f'K SPEC 18.1 speaker entry {n}: team {row.get("team")!r} playable {row.get("playable")!r} '
                f'(want team none, not playable)')
if heroes_build:
    # the heroes module (SPEC_heroes.md) replaced XML2's herostat and moved the heroes used as NPCs out of npcstat:
    # compare the npcstat part of the plan only
    # (and promoted npcstat heroes such as ProfXGladiator into herostat: heroes.ROSTER_NPC)
    out_hero = {s.get('name').lower() for s in tabs[('herostat', 'engb')]} if ('herostat', 'engb') in tabs else set()
    plan_npc = plan['names'] - {n.lower() for n in plan['herostat']} - {h.lower() for h in plan['heroes_as_npc']} - \
        out_hero
    out_npc = {s.get('name').lower() for s in tabs[('npcstat', 'engb')]} - speakers
    if plan_npc != out_npc:
        err(f"K planned_stats npcstat names differ from <out>: only plan {sorted(plan_npc - out_npc)[:8]}, "
            f"only out {sorted(out_npc - plan_npc)[:8]}")
elif plan['names'] != stats_names_all:
    err(f"K planned_stats names differ from <out>: only plan {sorted(plan['names'] - stats_names_all)[:8]}, "
        f"only out {sorted(stats_names_all - plan['names'])[:8]}")
if sorted(h.lower() for h in plan['heroes_as_npc']) != sorted(h.lower() for h in detail['heroes_as_npc']):
    err(f"K heroes_as_npc differ: plan {plan['heroes_as_npc']} vs build {detail['heroes_as_npc']}")
# SPEC 5.1 (zone .chr / spawners: beast, frost, jubilee, magma, psylocke) + SPEC 12.2 (conversation speakers and
# unlockCharacter / setInCampaign literals: profxastral)
if {h.lower() for h in plan['heroes_as_npc']} != {'beast', 'frost', 'jubilee', 'magma', 'profxastral', 'psylocke'}:
    err(f"K heroes_as_npc {plan['heroes_as_npc']} != SPEC's beast, frost, jubilee, magma, profxastral, psylocke")
kept_out = {s.get('name').lower() for s in tabs[('npcstat', 'engb')]} - x1_origin - speakers
if kept_out != set(plan['keep_x2']):
    err(f"K kept XML2 entries differ: plan {sorted(plan['keep_x2'])} vs out {sorted(kept_out)}")
info.append(f"K: planned_stats predicts {len(plan['names'])} names, {len(plan['heroes_as_npc'])} heroes as NPC, "
            f"{len(plan['keep_x2'])} kept XML2 entries; {len(speakers)} SPEC 18.1 speaker entries")

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
