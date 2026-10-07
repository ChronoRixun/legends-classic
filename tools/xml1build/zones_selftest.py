"""Offline self-test of the zones module's output (read-only).

usage: python -m xml1build.zones_selftest <out dir> [--base "<XML2 folder>"]
       (run from tools/)

Decodes every file the zones module registered and checks it against the SPEC 5.3 contract and the XML1
sources: XMLB validity (decode, byte-identical re-encode, lowercase+sorted attributes, > 8 bytes), per-zone
file set, zone XML element count vs source, world entity (zonescript resolves, soundfile < 10), links
(nextzone/prevzone resolve same-dir or full), inline scripts <= 255 bytes, no backslashes in script refs, CHRB
names vs research/sweep/zones.json, package shape (zonexml/characters/boy, boy last, nav iff NAVB, no
fre/ger, lowercase, no duplicates) and every package entry resolving in <out> or, for characters/scripts
files when those modules did not run, in their planned sets; zoneinfo (XML2 entries untouched, one entry per
converted zone), world tables (XML2 entries preserved in order), permanent.PKGB (prefix preserved), the base
files the module replaced, and the proven nyc1_1_1 package (xml2_test) being a subset of ours; XML1's XP pickups
(SPEC 23.1: XP_<XML1 count> items with --xp-curve xml1, the one XP item with xml2; count 1).
Prints a summary and exits 1 on any failure.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from xml1build import common as C          # noqa: E402
from xml1build.zones import HERO_STYLE_PREFIX   # noqa: E402  (section 28)

FAIL = collections.defaultdict(list)
_PLAYABLE = {}


def playable_heroes(out):
    """the build's playable hero names (lower case), from heroes' own record (_build/heroes_detail.json)."""
    key = str(out)
    if key not in _PLAYABLE:
        try:
            rec = json.loads((Path(out) / '_build' / 'heroes_detail.json').read_text(encoding='utf-8'))
            _PLAYABLE[key] = frozenset(h.lower() for h in rec.get('heroes', {}))
        except (OSError, ValueError):
            _PLAYABLE[key] = frozenset()
    return _PLAYABLE[key]
INFO = collections.Counter()
# research/sweep/zones.json: 20 prevzone values point nowhere + 1 ambiguous (demo/deck/arb_fd1 'arb_fd2')
KNOWN_UNRESOLVED_PREVZONE = 21
EXPECTED_BASE_REPLACED = re.compile(
    r'^(data/(zoneinfo|common_ents|item_ents|items|shared_nodes)\.(xmlb|engb)|'
    r'packages/generated/(common_ents|item_ents|items|shared_nodes|maps/package/permanent|'
    r'maps/package/permanent_fightstyles|maps/menu/main_back)\.pkgb|'
    r'maps/menu/main_back\.(xmlb|chrb|igb|navb|boyb)|conversations/common/finish_obj\.(xmlb|engb)|'
    r'motionpaths/(common/cabinet_knockedover|common/table_knockedover|menus/main_back)\.igb|'
    r'actors/zone_dr_mag03\.igb|'
    r'models/puzzles/beacon_xtraction(_noteamchange|_saveonly)?\.igb)$'
)            # section 16: XML1's dr_mag03 leaf equals an XML2 zone DB name; the three beacons XML2 retail
               # same-names lost the glow material and are force-imported XML1-wins (issue #74, SPEC
               # "(number assigned at merge)"); beacon_xtraction_mastermold overwrites no base file


def fail(kind, msg):
    FAIL[kind].append(msg)


def decode(path):
    return C.decode_xmlb(Path(path).read_bytes())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--base', default=str(C.DEFAULT_BASE))
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    ctx = C.BuildContext(out, a.base, args=C.args_for_out(out, a.base))      # the build's own options (SPEC 21)
    reg = C.Registry.load(out / '_build/registry.json')
    detail = json.loads((out / '_build/zones_detail.json').read_text(encoding='utf-8'))
    zones_json = ctx.zones_info
    nsmap = ctx.nsmap
    owned = {k: e for k, e in reg.entries.items() if e['owner'] == 'zones'}
    INFO['files_owned'] = len(owned)
    owners = collections.Counter(e['owner'] for e in reg.entries.values())

    # planned sets for files of modules that may not have run
    try:
        from xml1build import scripts as S
        planned_scripts = set(S.planned_script_refs(ctx))
    except Exception:                       # noqa: BLE001
        from xml1build import zones_providers as P
        planned_scripts = set(P.research_script_refs(ctx))
    skins = set(nsmap['skins'].values())
    animdbs = {v.lower() for v in nsmap['animdbs'].values()}
    pstyles = {v.lower() for v in nsmap['powerstyles'].values()}
    fstyles = {v.lower() for v in nsmap['fightstyles'].values()}

    def planned(kind, fn):
        k = kind.lower()
        if k == 'actorskin':
            return fn in skins or ctx.base_exists(f'actors/{fn}.igb')
        if k == 'actoranimdb':
            return fn in animdbs or fn in skins or ctx.base_exists(f'actors/{fn}.igb')
        if k == 'fightstyle':
            d, _, n = fn.rpartition('/')
            return (n in pstyles if d == 'data/powerstyles' else n in fstyles) or \
                bool(ctx.base_index.find(fn, ('.XMLB', '.engb')))
        if k == 'model' and re.search(r'(hud_head_|/characters/)(\d{5})$', fn):
            m = re.search(r'^(.*?)(\d{5})$', fn)
            src = m.group(1) + f'{int(m.group(2)) - 14000:04d}.igb'
            return ctx.x1_path(src) is not None or ctx.base_exists(fn + '.igb')
        if k == 'script':
            return C.script_ref(fn) in planned_scripts or ctx.base_exists(fn + '.py')
        if fn.startswith('dialogs/x1/'):
            return (ctx.research_path('scripts/out') / (fn + '.XMLB')).is_file()
        return False

    # A. every zones-owned file exists with its size; XMLB family valid
    for k, e in owned.items():
        p = out / e['rel']
        if not p.is_file():
            fail('A_missing_file', e['rel'])
            continue
        if p.stat().st_size != e['size']:
            fail('A_size', e['rel'])
        if C.split_ext(k)[1] in C.XMLB_FAMILY:
            data = p.read_bytes()
            if len(data) <= 8:
                fail('A_header_only', e['rel'])
                continue
            try:
                root = C.decode_xmlb(data)
            except Exception as ex:          # noqa: BLE001
                fail('A_decode', f'{e["rel"]}: {ex}')
                continue
            probs = C.xmlb_attr_problems(root)
            if probs:
                fail('A_attrs', f'{e["rel"]}: {probs[:2]}')
            if C.xmlb.encode(root) != data:
                fail('A_reencode', e['rel'])
            INFO['xmlb_checked'] += 1
    # F. base files replaced
    for k, e in owned.items():
        if e['overwrote_base']:
            INFO['base_replaced'] += 1
            if not EXPECTED_BASE_REPLACED.match(k):
                fail('F_unexpected_base_replace', e['rel'])

    converted = detail['converted']
    conv_set = set(converted)
    INFO['zones_converted'] = len(converted)
    INFO['zones_skipped'] = len(detail['skipped'])
    unresolved_prev = 0
    for z in converted:
        d = detail['zones'][z]
        src = d['zonexml']
        ext = C.split_ext(src)[1]
        need = [f'maps/{z}.xmlb', f'maps/{z}.chrb', f'maps/{z}.boyb', f'maps/{z}.igb',
                f'packages/generated/maps/{z}.pkgb'] + ([f'maps/{z}.engb'] if ext == '.eng' else [])
        for n in need:
            if n not in owned:
                fail('B_zone_file_missing', n)
        if d['has_nav'] != (f'maps/{z}.navb' in owned):
            fail('B_nav_flag', z)
        if f'maps/{z}.navb' in owned and ctx.x1_is_empty(f'maps/{z}.nav'):
            fail('B_nav_from_empty', z)
        # zone XML vs source (+1 element where zones added the missing world entity)
        o = decode(out / owned[f'maps/{z}.xmlb']['rel'])
        s = ctx.read_x1_xml(src)
        synth = bool(d.get('world_synthesized'))
        if synth:
            INFO['zones_world_synthesized'] += 1
            if C.find_world(s) is not None:
                fail('B_world_synth_but_source_has_one', z)
        if sum(1 for _ in o.iter()) != sum(1 for _ in s.iter()) + (1 if synth else 0):
            fail('B_element_count', z)
        if o.tag != 'world':
            fail('B_root_tag', f'{z}: <{o.tag}>')
        # precache filenames: lowercase '/' paths (XML2 convention), script refs normalised
        for el in o.iter('precache'):
            t, f = (el.get('type') or '').lower(), el.get('filename') or ''
            if t != 'sound' and '(' not in f and (f != f.lower() or '\\' in f):
                fail('B_precache_not_normalised', f'{z}: {t} {f}')
            if t == 'model' and f and not f.startswith(('models/', 'hud/', 'ui/', 'maps/', 'skybox/')):
                fail('B_precache_model_path', f'{z}: {f}')
        if ext == '.eng' and (out / owned[f'maps/{z}.engb']['rel']).read_bytes() != \
                (out / owned[f'maps/{z}.xmlb']['rel']).read_bytes():
            fail('B_xmlb_engb_differ', z)
        w = C.find_world(o)
        if w is None:
            fail('B_no_world', z)
        else:
            zs = w.get('zonescript')
            if zs and C.script_ref(zs) not in planned_scripts and not ctx.base_exists(C.script_rel(zs)):
                fail('B_zonescript_unresolved', f'{z}: {zs}')
            if zs:
                INFO['zones_with_zonescript'] += 1
            sf = w.get('soundfile') or ''
            if len(sf) >= 10:
                fail('B_soundfile_len', f'{z}: {sf}')
            if sf and not any(ctx.sound_bank_rel(f'{sf}_{c}') for c in 'macvd'):
                fail('B_soundfile_no_bank', f'{z}: {sf}')
            if sf != sf.strip():
                fail('B_soundfile_whitespace', f'{z}: {sf!r}')
            if (w.get('soundfile') or '') != (C.find_world(s).get('soundfile') or '' if C.find_world(s) is not None
                                               else ''):
                INFO['zones_soundfile_changed'] += 1
        for el in o.iter():
            for k, v in el.attrib.items():
                if '(' in v and len(v.encode('latin-1', 'replace')) > 255:
                    fail('B_inline_255', f'{z} {el.tag}@{k}')
                if (k.endswith('script') or k.endswith('scriptfile')) and '(' not in v and '\\' in v \
                        and '\\n' not in v:
                    fail('B_backslash_script_ref', f'{z} {k}={v}')
                if k in ('nextzone', 'prevzone') and v.strip():
                    t = v.strip()
                    full = t if '/' in t else f'{z.rsplit("/", 1)[0]}/{t}'
                    if f'maps/{full}.xmlb' not in ctx.out_index:
                        if k == 'prevzone':
                            unresolved_prev += 1
                        else:
                            fail('B_nextzone_unresolved', f'{z}: {t}')
                    if t != t.lower() or '\\' in t:
                        fail('B_link_not_normalised', f'{z}: {t}')
                if k == 'tilemodelfolder' and v != v.lower():
                    fail('B_tilefolder_case', f'{z}: {v}')
        # CHRB vs sweep baseline
        chr_names = [e.get('name') for e in decode(out / owned[f'maps/{z}.chrb']['rel']).iter()
                     if e.tag == 'character']
        exp = zones_json.get(z, {}).get('chr_characters', [])
        if sorted(n.lower() for n in chr_names) != sorted(n.lower() for n in exp):
            fail('B_chr_vs_sweep', f'{z}: {chr_names} vs {exp}')
        # package
        pk = decode(out / owned[f'packages/generated/maps/{z}.pkgb']['rel'])
        ents = [(e.tag, e.get('filename')) for e in pk]
        kinds = [k for k, _ in ents]
        for k in ('zonexml', 'characters', 'boy'):
            if k not in kinds:
                fail('B_pkg_core', f'{z}: no {k}')
        # boy last, or boy then the zone's own automap (section 26; XML2's packages end ... boy, zam)
        tail = ents[:-1] if ents[-1] == ('zam', f'automaps/{z}') else ents
        if tail[-1] != ('boy', f'maps/{z}'):
            fail('B_pkg_boy_last', z)
        if any(k == 'zam' for k, _ in tail) or any(k == 'texture' and f.startswith('textures/automap/')
                                                   for k, f in ents):
            fail('B_pkg_automap', f'{z}: a <zam> before boy or a textures/automap entry (section 26)')
        if ('nav' in kinds) != d['has_nav']:
            fail('B_pkg_nav', z)
        if len(set((k, f.lower()) for k, f in ents)) != len(ents):
            fail('B_pkg_duplicates', z)
        for k, f in ents:
            if f != f.lower() or '\\' in f:
                fail('B_pkg_case', f'{z}: {k} {f}')
            if f.endswith(('.fre', '.ger', '.eng', '.xml', '.igb', '.py')):
                fail('B_pkg_ext', f'{z}: {k} {f}')
            if k == 'motionpath' and f.count('/') < 2:
                fail('B_motionpath_form', f'{z}: {f}')
            cands = C.package_entry_files(k, f)
            if cands is None:
                continue
            INFO['pkg_entries_checked'] += 1
            if any(c in ctx.out_index for c in cands):
                continue
            if planned(k, f):
                INFO['pkg_entries_planned_other_module'] += 1
                continue
            fail('B_pkg_unresolved', f'{z}: {k} {f}')
        # the zone script / every script entry must be listed
        if w is not None and w.get('zonescript') and ('script', f'scripts/{w.get("zonescript")}') not in ents:
            fail('B_pkg_zonescript_not_listed', z)
        # section 28: a playable hero's power style in the package lists his talents first (Cyclops's empty wheel);
        # villains' x1_ps_* styles (Toad, Juggernaut, ...) are not heroes and stay as XML1 listed them
        for i, (k, f) in enumerate(ents):
            if k == 'fightstyle' and f.startswith(HERO_STYLE_PREFIX):
                hero = f[len(HERO_STYLE_PREFIX):]
                if hero not in playable_heroes(out):
                    continue
                if ('xml_talents', f'data/talents/{hero}') in ents[:i]:
                    INFO['pkg_hero_styles_with_talents_first'] += 1
                else:
                    fail('B_pkg_hero_style_before_talents', f'{z}: {f} (section 28)')
    INFO['prevzone_unresolved'] = unresolved_prev
    if unresolved_prev > KNOWN_UNRESOLVED_PREVZONE:
        fail('B_prevzone_unresolved', f'{unresolved_prev} > {KNOWN_UNRESOLVED_PREVZONE}')

    # C. zoneinfo
    for ext in ('.XMLB', '.engb'):
        b = decode(ctx.base_index.path(f'Data/zoneinfo{ext}'))
        o = decode(ctx.out_index.path(f'Data/zoneinfo{ext}'))
        bz = [dict(e.attrib) for e in b]
        oz = [dict(e.attrib) for e in o]
        # XML2 entries unchanged except the Xtraction network attributes of XML2's non-town-centre destinations
        # (section 15, zones.XTRACTION_STRIP_XML2_DESTINATIONS); XML2's 5 act town centres keep theirs
        from xml1build.zones import XTRACTION_ATTRS, XTRACTION_CAP

        def town(e):
            return (e.get('towncenter') or '').lower() == 'true'
        for i, e in enumerate(bz):
            want = e if town(e) else {k: v for k, v in e.items() if k not in XTRACTION_ATTRS}
            if e['name'] != 'menu/main_back' and oz[i] != want:
                fail('C_zoneinfo_xml2_changed', f'{ext} {e["name"]}')
        xt = [e['name'] for e in oz if any(k in e for k in XTRACTION_ATTRS) and not town(e)]
        if xt:
            fail('C_zoneinfo_xtraction_left', f'{ext} {xt[:5]}')
        INFO[f'zoneinfo{ext}_xtraction_stripped'] = sum(1 for e in bz if any(k in e for k in XTRACTION_ATTRS)
                                                        and not town(e))
        # section 15: one registered town centre per selectable act, within XMen2.exe's 31-entry table
        xe = [e for e in oz if (e.get('extraction') or '').lower() == 'true']
        if len(xe) > XTRACTION_CAP:
            fail('C_zoneinfo_xtraction_cap', f'{ext} {len(xe)} > {XTRACTION_CAP}')
        tcs = {int(e.get('act') or 1): e['name'] for e in xe if town(e)}
        tcd = detail.get('towncenters') or {}
        for a, z in (tcd.get('towncenters') or {}).items():
            if tcs.get(int(a)) != z:
                fail('C_zoneinfo_towncenter', f'{ext} act {a}: {tcs.get(int(a))} != {z}')
        for a, z in (tcd.get('added') or {}).items():
            e = next((e for e in oz if e['name'] == z), None)
            if e is None or e.get('extraction') != 'true' or not town(e) or e.get('act') != str(a) \
                    or not e.get('savename') or not e.get('mapx') or not e.get('mapy') or z not in conv_set:
                fail('C_zoneinfo_towncenter_attrs', f'{ext} act {a} {z}: {e}')
        INFO[f'zoneinfo{ext}_towncenters'] = len(tcs)
        INFO[f'zoneinfo{ext}_towncenters_added'] = len(tcd.get('added') or {})
        names = collections.Counter(C.norm(e['name']) for e in oz)
        for z in converted:
            if names[z] != 1:
                fail('C_zoneinfo_count', f'{ext} {z}: {names[z]}')
        for e in oz[len(bz):]:
            if not e.get('act', '').isdigit() or e.get('build') != 'normal' or e.get('state') != '1':
                fail('C_zoneinfo_attrs', f'{ext} {e}')
            lo = e.get('loading')
            if lo:
                if re.fullmatch(r'textures/loading/\d+', lo):
                    if not (ctx.out_index.find(lo, ('.IGB',)) or ctx.x1_path(
                            f'textures/loading/{int(lo.rsplit("/", 1)[1]) - 14000:04d}.igb')):
                        fail('C_loading_numeric', lo)
                elif not ctx.out_index.find(lo, ('.IGB', '.png')):
                    fail('C_loading_named', lo)
        tut = [e for e in oz if e['name'] == 'act0/tutorial/tutorial1']
        if not tut or tut[0].get('state') != '2':
            fail('C_tutorial_state', ext)
        INFO[f'zoneinfo{ext}_entries'] = len(oz)

    # D. world tables: XML2 children preserved in order, additions new names only
    for name in ('common_ents', 'item_ents', 'items', 'shared_nodes'):
        for ext in ('.XMLB', '.engb'):
            bp = ctx.base_index.path(f'Data/{name}{ext}')
            if bp is None:
                continue
            b = C.iter_roots(decode(bp))[0]
            o = C.iter_roots(decode(ctx.out_index.path(f'Data/{name}{ext}')))[0]
            bl, ol = list(b), list(o)
            if [C.xmlb.encode(x) for x in bl] != [C.xmlb.encode(x) for x in ol[:len(bl)]]:
                fail('D_world_table_xml2_changed', f'{name}{ext}')
            have = {(x.get('name') or '').lower() for x in bl}
            added = ol[len(bl):]
            if any((x.get('name') or '').lower() in have for x in added):
                fail('D_world_table_dup_name', f'{name}{ext}')
            INFO[f'{name}{ext}_added'] = len(added)
        # package prefix preserved + appended entries resolve
        for rel in (f'Packages/generated/{name}.PKGB',):
            b = [(e.tag, e.get('filename')) for e in decode(ctx.base_index.path(rel))]
            o = [(e.tag, e.get('filename')) for e in decode(ctx.out_index.path(rel))]
            if o[:len(b)] != [(k, C.norm(f)) for k, f in b] and o[:len(b)] != b:
                fail('D_pkg_prefix', rel)
            for k, f in o[len(b):]:
                c = C.package_entry_files(k, f)
                if c and not any(x in ctx.out_index for x in c) and not planned(k, f):
                    fail('D_pkg_unresolved', f'{rel}: {k} {f}')
    # E. permanent
    rel = 'Packages/generated/maps/package/permanent.PKGB'
    b = [(e.tag, e.get('filename')) for e in decode(ctx.base_index.path(rel))]
    o = [(e.tag, e.get('filename')) for e in decode(ctx.out_index.path(rel))]
    if [(k, C.norm(f)) for k, f in o[:len(b)]] != [(k, C.norm(f)) for k, f in b]:
        fail('E_permanent_prefix', rel)
    for k, f in o[len(b):]:
        c = C.package_entry_files(k, f)
        if c and not any(x in ctx.out_index for x in c):
            fail('E_permanent_unresolved', f'{k} {f}')
    INFO['permanent_appended'] = len(o) - len(b)
    # E2. permanent_fightstyles: XML2 prefix preserved, XML1-only entries appended, all resolve, fightstyle_villain
    rel = 'Packages/generated/maps/package/permanent_fightstyles.PKGB'
    b = [(e.tag, e.get('filename')) for e in decode(ctx.base_index.path(rel))]
    o = [(e.tag, e.get('filename')) for e in decode(ctx.out_index.path(rel))]
    if [(k, C.norm(f)) for k, f in o[:len(b)]] != [(k, C.norm(f)) for k, f in b]:
        fail('E2_permanent_fightstyles_prefix', rel)
    for k, f in o:
        c = C.package_entry_files(k, f)
        if c and not any(x in ctx.out_index for x in c):
            fail('E2_permanent_fightstyles_unresolved', f'{k} {f}')
    if ('fightstyle', 'data/fightstyles/fightstyle_villain') not in o or ('actoranimdb', 'fightstyle_villain') not in o:
        fail('E2_fightstyle_villain_not_resident', rel)
    INFO['permanent_fightstyles_appended'] = len(o) - len(b)

    # H. proven nyc1_1_1 package (xml2_test, in-game OK) must be a subset of ours (after the +14000 mapping)
    proven = ctx.root / 'xml2_test/Packages/generated/maps/nyc/alison/nyc1_1_1.PKGB'
    if proven.is_file() and 'nyc/alison/nyc1_1_1' in conv_set:
        ours = {(e.tag, e.get('filename')) for e in decode(out / owned['packages/generated/maps/nyc/alison/'
                                                                        'nyc1_1_1.pkgb']['rel'])}
        for e in decode(proven):
            # convert_zone wrote 'effects/<x>' and 'actors/<id>'; SPEC 3.5 uses XML2's bare forms
            k, f = e.tag, C.norm(e.get('filename'))
            if k in ('actorskin', 'actoranimdb'):
                f = C.map_animdb(f[len('actors/'):] if f.startswith('actors/') else f)
                if k == 'actoranimdb' and f.startswith('mission_'):
                    f = 'zone_nyc1_1_1'          # section 16: the area mission DB is installed as zone_<leaf>
            elif k == 'effect' and f.startswith('effects/'):
                f = f[len('effects/'):]
            elif k == 'texture' and f.startswith('textures/automap/'):
                k, f = 'zam', 'automaps/nyc/alison/nyc1_1_1'      # section 26: the XML1 texture -> the zone's .zam
            if (k, f) not in ours:
                fail('H_proven_entry_missing', f'{k} {f}')
        INFO['nyc1_1_1_entries'] = len(ours)
        # section 16: the proven zone's package lists its own zone DB and never a mission_* DB
        if ('actoranimdb', 'zone_nyc1_1_1') not in ours:
            fail('H_zone_animdb_missing', 'actoranimdb zone_nyc1_1_1')
        if any(k == 'actoranimdb' and C.norm(f).startswith('mission_') for k, f in ours):
            fail('H_mission_animdb_listed', 'nyc1_1_1')

    # I. remapped XML1 scan turrets whose deathscripts gate progression stay fixed mounts (x1schema.TURRET_MOUNT_FLAGS)
    from xml1build import x1schema as XS
    turrets = {'haarp/ext/haarp_ext02': 'tank_turret', 'haarp/ext/haarp_ext04': 'tank_turret',
               'hive/h_ext/hive1_1_1': 'tank_turret_sp01'}
    for z, name in turrets.items():
        if z not in conv_set:
            continue
        for ext in ('.xmlb', '.engb'):
            e = owned.get(f'maps/{z}{ext}')
            if e is None:
                continue
            ents = [el for el in decode(out / e['rel']).iter() if el.get('name') == name and el.get('classname')]
            if not ents:
                fail('I_turret_missing', f'{z}{ext} {name}')
            for el in ents:
                if el.get('classname') != 'physent' or not el.get('deathscript') or \
                        any(el.get(k) != v for k, v in XS.TURRET_MOUNT_FLAGS):
                    fail('I_turret_not_fixed_mount', f'{z}{ext} {name}: {dict(el.attrib)}')
                INFO['turrets_fixed_mount'] += 1

    # J. SPEC 23.1: XML1's XP pickups. xml1 curve: each names XP_<its XML1 count>, whose item gives that XP to the
    # activator; xml2: the one XP item (5000 to the roster). Both: count 1 (XMen2.exe's 16-bit quantity, 0x47a970)
    from xml1build import zones as Z
    curve = C.xp_curve_mode(ctx)
    INFO['xp_curve'] = curve
    items = {}
    for ext in ('.xmlb', '.engb'):
        e = reg.entries.get(f'data/items{ext}')
        if e is not None:
            items.update({(i.get('name') or '').lower(): i for i in decode(out / e['rel']).iter('item')
                          if i.get('name')})
    for k, e in owned.items():
        if not (k.startswith('maps/') and k.endswith('.xmlb')) or not e.get('source'):
            continue
        src = Path(e['source'])
        if src.suffix.lower() not in ('.eng', '.xml'):
            continue
        x1 = {el.get('name'): el for el in C.parse_x1_text(src).iter()
              if (el.get('inventoryitem') or '').lower() == 'xp' and el.get('name')}
        if not x1:
            continue
        for el in decode(out / e['rel']).iter():
            src_el = x1.get(el.get('name'))
            if src_el is None or el.get('inventoryitem') is None:
                continue                                # the placements (<inst>) share the entity's name
            amount = int(src_el.get('count') or 0)
            want = Z.XP_PICKUP_ITEM.format(item='XP', amount=amount) if curve == 'xml1' else 'XP'
            item = items.get(want.lower())
            want_act = Z.XP_PICKUP_SCRIPT.format(amount=amount) if curve == 'xml1' else \
                Z.ITEM_TYPE_MAP['xp'][1]['onactivate']
            if el.get('inventoryitem') != want or el.get('count') not in (None, '1'):
                fail('J_xp_pickup_entity', f'{k} {el.get("name")}: inventoryitem {el.get("inventoryitem")} count '
                                           f'{el.get("count")} (want {want}, 1)')
            elif item is None or item.get('onactivate') != want_act or item.get('activateonpickup') != 'true':
                fail('J_xp_pickup_item', f'{want}: {item is not None and dict(item.attrib)} (want onactivate '
                                         f'{want_act})')
            else:
                INFO['xp_pickups'] += 1

    # J2. SPEC 32: XML1's SKILL pickups keep XML1's item (SKILL), whose onactivate is xml2-fix's
    # addSkillPoints('_ACTIVATOR_',1) - one unspent skill point to the picker, never the roster award (awardXPToPlayable)
    for k, e in owned.items():
        if not (k.startswith('maps/') and k.endswith('.xmlb')) or not e.get('source'):
            continue
        src = Path(e['source'])
        if src.suffix.lower() not in ('.eng', '.xml'):
            continue
        sroot = C.parse_x1_text(src)
        x1 = {el.get('name'): el for el in sroot.iter()
              if (el.get('inventoryitem') or '').lower() == 'skill' and el.get('name')}
        if not x1:
            continue
        want_act = Z.SKILL_PICKUP_SCRIPT
        for el in decode(out / e['rel']).iter():
            if x1.get(el.get('name')) is None or el.get('inventoryitem') is None:
                continue
            item = items.get((el.get('inventoryitem') or '').lower())
            if (el.get('inventoryitem') or '').lower() != 'skill':
                fail('J_skill_pickup_entity', f'{k} {el.get("name")}: inventoryitem {el.get("inventoryitem")} '
                                              f'(want SKILL, XML1\'s own item)')
            elif item is None or item.get('onactivate') != want_act or item.get('activateonpickup') != 'true':
                fail('J_skill_pickup_item', f'SKILL: {item is not None and dict(item.attrib)} (want onactivate '
                                            f'{want_act})')
            else:
                INFO['skill_pickups'] += 1
    roster = sorted(n for n, i in items.items() if 'awardxptoplayable' in (i.get('onactivate') or '').lower()
                    and n.startswith('skill'))
    if roster:
        fail('J_skill_roster_award', f'skill items still award the roster: {roster}')
    # J3. SPEC 32.1: XMen2.exe registers no item past the overflow of its enhancement pool (375 records; the fix's
    # [Limits] ItemEnhancements, 512 for the port, is what Z.ITEM_ENHANCEMENT_POOL checks against), so the pickup
    # items (SKILL, XP_*) must sit before it
    for ext in ('.xmlb', '.engb'):
        e = reg.entries.get(f'data/items{ext}')
        if e is None:
            continue
        lost = [n for n, _ in Z.enhancement_pool_cut(C.iter_roots(decode(out / e['rel']))[0])]
        INFO[f'items_beyond_enhancement_pool{ext}'] = len(lost)
        bad = [n for n in lost if (n or '').upper().startswith(('SKILL', 'XP_'))]
        if bad:
            fail('J_pickup_item_not_loaded', f'data/items{ext}: {bad} lie past the enhancement pool overflow')

    print(f'zones self-test of {out}')
    print('  registry owners:', dict(owners))
    for k, v in sorted(INFO.items()):
        print(f'  {k}: {v}')
    n = sum(len(v) for v in FAIL.values())
    for kind, msgs in sorted(FAIL.items()):
        print(f'FAIL {kind}: {len(msgs)}')
        for m in msgs[:8]:
            print('      ', m)
    print('RESULT:', 'PASS' if not n else f'FAIL ({n})')
    return 1 if n else 0


if __name__ == '__main__':
    sys.exit(main())
