"""Prototype: convert XML1 NPC(s) into XML2 PC form using the x1names namespace, into a scratch tree
that mirrors the XML2 install (drop-in overlay).

usage: python build_chars.py [--variant scheme|orig|animprefix] [--drop varese,...] [--out DIR] NAME [NAME...]
       python build_chars.py --all-npcs --mode xml1 --out DIR      (scalability dry run, all 190 NPCs)

variants (for bisecting an in-game failure):
  scheme      (default) skin renumbered 5810->19810 incl. in-IGB names; anim DBs renamed only on collision
  orig        keep XML1 skin number/filenames (5810) - only valid where XML2 has no file of that name
  animprefix  like scheme, and additionally forces 'x1_' on the character anim DB to exercise that rename
modes:
  additive    (default) XML2 npcstat + new entries; to respect the 296-name table (XMen2.exe 0x44c1a7
              cmp 0x129) XML2 entries named in --drop (default: varese) are removed first
  xml1        npcstat = XML2 entries kept by --keep-x2 (MC placeholders + exe-referenced names) + XML1 NPCs

Writes <out>/... files and <out>/_build_report.json; run validate.py <out> afterwards.
"""
import argparse, copy, json, os, re, sys
import xml.etree.ElementTree as ET
from common import *
import x1names as N

ap = argparse.ArgumentParser()
ap.add_argument('names', nargs='*')
ap.add_argument('--variant', default='scheme', choices=['scheme', 'orig', 'animprefix'])
ap.add_argument('--mode', default='additive', choices=['additive', 'xml1'])
ap.add_argument('--drop', default='varese')
ap.add_argument('--keep-x2', default='_hero1_mc_,_hero2_mc_,_hero3_mc_,_hero4_mc_,'
                'abyss,apocdummy,archangel,bastion,beast,forge,garokk,holocaust,menu,mikhail,omegared,profx,'
                'sauron,scarabapoc,stryfe,sugarman',
                help='xml1 mode: XML2 npcstat entries to keep (default: MC placeholders + npcstat names that '
                     'appear as strings in XMen2.exe, see x2_stats_refs.json); XML1 entries of the same name win')
ap.add_argument('--all-npcs', action='store_true')
ap.add_argument('--out', default=os.path.join(HERE, 'out', 'grso_riot'))
args = ap.parse_args()

OUT = args.out
idx2 = x2_index()
files1 = x1_files()
man = manifest()
report = {'variant': args.variant, 'mode': args.mode, 'written': [], 'deferred': [], 'dropped_attrs': [],
          'dropped_x2_entries': [], 'added_talents': [], 'notes': []}

XML2_TAG = {'talent': 'talent', 'race': 'Race', 'bolton': 'BoltOn', 'multipart': 'Multipart', 'flyeffect': 'FlyEffect'}
DROP_ATTRS = {'leader', 'ratingmelee', 'ratingranged', 'ratingsupport', 'ratingdurability', 'throwally'}
COSTUMES_X2 = {'astonishing', 'aoa', '60s', '70s', 'weaponx', 'future', 'winter', 'civilian'}
x1_weapons = {w.get('name').lower(): {k.lower(): v for k, v in w.attrib.items()}
              for w in parse_x1_text(f'{X1L}/data/weapons/weapons.eng').iter('weapon')}
x2_shared_talents = load_xmlb(f'{X2}/Data/shared_talents.XMLB')
x2_shared_talents_eng = load_xmlb(f'{X2}/Data/shared_talents.engb')
x2_talent_names = {t.get('name').lower() for t in x2_shared_talents.iter('talent')}
x1_shared = {t.get('name').lower(): t for t in parse_x1_text(f'{X1L}/data/shared_talents.eng').iter()
             if t.tag.lower() == 'talent'}
x2_banks = {os.path.splitext(os.path.basename(p))[0].lower() for p in idx2 if p.startswith('sounds/eng/')}


def sorted_attrs(el):
    for e in el.iter():
        e.attrib = dict(sorted((k.lower(), v) for k, v in e.attrib.items()))
    return el


def emit(rel, data):
    dst = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'wb').write(data)
    if rel not in report['written']:
        report['written'].append(rel)


def skin_of(s):
    if args.variant == 'orig':
        return s
    return N.map_skin(s)


def animdb_of(a):
    if not a:
        return a
    if N.is_skin_id(a):
        return skin_of(a)
    m = N.map_animdb(a)
    if args.variant == 'animprefix' and not m.startswith('x1_') and not N.shares_xml2_animdb(a):
        m = 'x1_' + a
    return m


# ------------------------------------------------------------------ files
copied = {}


def copy_actor(stem, kind):
    """XML1 actors/<stem>.igb -> XML2 Actors/<new>.IGB (skins get in-IGB names patched). Returns new stem."""
    if stem in copied:
        return copied[stem]
    src = files1.get(f'actors/{stem.lower()}.igb')
    new = skin_of(stem) if N.is_skin_id(stem) else animdb_of(stem)
    if src is None:
        raise SystemExit(f'XML1 has no actors/{stem}.igb')
    if f'actors/{new.lower()}.igb' in idx2:
        # shared with XML2 (identical or intentionally shared): never overwrite XML2's file
        if new == stem and status(f'actors/{stem.lower()}.igb') != 'identical':
            if N.shares_xml2_animdb(stem):
                report['notes'].append(f'actors/{stem}: shared XML2 anim DB used (global/fightstyle DB)')
            elif args.variant == 'orig':
                report['notes'].append(f'variant orig: actors/{stem} collides with XML2; XML2 version will be used')
            else:
                raise SystemExit(f'actors/{stem} collides with XML2 but is not renamed')
        copied[stem] = new
        return new
    data = open(src, 'rb').read()
    if N.is_skin_id(stem) and new != stem:
        data, n, problems = N.igb_rename(data, stem, new)
        report['notes'].append(f'actors/{stem}.igb -> Actors/{new}.IGB: {n} in-IGB names renamed')
        assert not problems, problems
    emit(f'Actors/{new}.IGB', data)
    copied[stem] = new
    return new


def copy_ui(rel_x1):
    """hud/hud_head_<id>.igb, ui/hud/characters/<id>.igb, ui/models/characters/<id>.igb.
    Package entry uses the exact lowercase form the exe formats at 0x5f4ec0 ('hud/hud_head_%s',
    'ui/hud/characters/%s', 'ui/models/characters/%s')."""
    if rel_x1 in copied:
        return copied[rel_x1]
    m = re.fullmatch(r'(hud/hud_head_|ui/hud/characters/|ui/models/characters/)(\d{4})\.igb', rel_x1)
    old = m.group(2)
    new = skin_of(old)
    entry = m.group(1) + new
    dst_rel = {'hud/hud_head_': 'HUD/hud_head_', 'ui/hud/characters/': 'UI/HUD/characters/',
               'ui/models/characters/': 'UI/models/characters/'}[m.group(1)] + new + '.IGB'
    copied[rel_x1] = entry
    if dst_rel.lower() in idx2:
        report['notes'].append(f'{rel_x1}: XML2 already has {dst_rel}; XML2 version used')
        return entry
    data = open(files1[rel_x1], 'rb').read()
    if new != old:
        data, n, problems = N.igb_rename(data, old, new)
        assert not problems
    emit(dst_rel, data)
    return entry


_COL = json.load(open(os.path.join(HERE, 'collisions.json')))


def status(rel):
    col = _COL
    for cat, d in col.items():
        for st, lst in d.items():
            if rel in lst:
                return st
    return None


_styles = {}


def style_file(kind, name):
    """make sure data/<kind>/<name> exists in XML2 or output; convert XML1's if needed. Returns xml2 name."""
    if (kind, name.lower()) not in _styles:
        _styles[(kind, name.lower())] = _style_file(kind, name)
    return _styles[(kind, name.lower())]


def _style_file(kind, name):
    mapped = N.map_powerstyle(name) if kind == 'powerstyles' else N.map_fightstyle(name)
    if f'data/{kind}/{mapped.lower()}.xmlb' in idx2:
        return mapped
    src = files1.get(f'data/{kind}/{name.lower()}.eng') or files1.get(f'data/{kind}/{name.lower()}.xml')
    if not src:
        report['deferred'].append(f'data/{kind}/{name}: not in XML1 either')
        return mapped
    root = sorted_attrs(parse_x1_text(src))
    data = xmlb.encode(root)
    emit(f'Data/{kind}/{mapped}.XMLB', data)
    if src.endswith('.eng'):
        emit(f'Data/{kind}/{mapped}.engb', data)
    report['notes'].append(f'converted data/{kind}/{name} -> {mapped} (XML1 content; power-system review pending)')
    return mapped


# ------------------------------------------------------------------ stats conversion
def ensure_talent(name, fightstyle):
    if name.lower() in x2_talent_names:
        return
    x2_talent_names.add(name.lower())
    t = ET.Element('talent', {'name': name})
    if fightstyle:
        t.set('fightstyle', 'true')
    ET.SubElement(t, 'level')
    report['added_talents'].append(name)
    for root in (x2_shared_talents, x2_shared_talents_eng):
        root.append(sorted_attrs(copy.deepcopy(t)))


def convert_stats(st):
    a = {k.lower(): v for k, v in st.attrib.items()}
    name = a['name']
    out = {}
    for k, v in a.items():
        if v == '' or k in DROP_ATTRS:
            report['dropped_attrs'].append((name, k, v))
            continue
        if k.startswith('skin_') and k[5:] not in COSTUMES_X2:
            report['dropped_attrs'].append((name, k, v))
            continue
        out[k] = v
    if 'skin' in out:
        out['skin'] = skin_of(out['skin'])
    if 'characteranims' in out:
        out['characteranims'] = animdb_of(out['characteranims'])
    for k in ('leaderskin', 'mutantskin'):
        if k in out:
            out[k] = skin_of(out[k])
    if 'powerstyle' in out:
        out['powerstyle'] = style_file('powerstyles', out['powerstyle'])
    if 'moveset1' in out:
        out['moveset1'] = style_file('fightstyles', out['moveset1'])
    if out.get('sounddir') and out['sounddir'].lower() not in x2_banks:
        report['deferred'].append(f"{name}: sounddir {out['sounddir']} has no PC bank "
                                  f"(needs Sounds/eng/{out['sounddir'][0]}/{out['sounddir'][1]}/{out['sounddir']}.zsm); attribute omitted")
        report['dropped_attrs'].append((name, 'sounddir', out.pop('sounddir')))
    weapon = x1_weapons.get(out.pop('weapon', '').lower())
    new = ET.Element('stats', out)
    fight_talent = False
    for c in st:
        tag = c.tag.lower()
        ca = {k.lower(): v for k, v in c.attrib.items()}
        if tag == 'talent':
            tn = ca['name']
            is_fs = tn.lower().startswith('fightstyle_')
            if is_fs:
                fight_talent = True
                tn = style_file('fightstyles', tn)
            ensure_talent(tn, is_fs or (x1_shared.get(tn.lower()) is not None and
                                        x1_shared[tn.lower()].get('fightstyle') == 'true'))
            e = {'name': tn}
            if ca.get('level'):
                e['level'] = ca['level']
            ET.SubElement(new, 'talent', e)
        elif tag == 'race':
            ET.SubElement(new, 'Race', {'name': ca['name']})
        elif tag == 'bolton':
            if 'model' in ca and N.is_skin_id(ca['model']):
                ca['model'] = copy_actor(ca['model'], 'bolton')
            if 'anim' in ca:
                ca['anim'] = animdb_of(ca['anim'])
                copy_actor(c.get('anim'), 'animdb')
            ca.pop('onlyprecache', None)
            ET.SubElement(new, 'BoltOn', ca)
        elif tag in ('multipart', 'flyeffect'):
            ET.SubElement(new, XML2_TAG[tag], ca)
        else:
            report['dropped_attrs'].append((name, '<' + tag + '>', 'hero-only XML1 child; needs hero conversion'))
    if weapon:
        b = {'bolt': weapon.get('actorbolt', 'Bip01 R Hand'), 'model': weapon['model'], 'slot': 'ebolton_weapon'}
        ET.SubElement(new, 'BoltOn', b)
        if weapon.get('accessorymodel'):
            ET.SubElement(new, 'BoltOn', {'bolt': weapon.get('accessorybolt', 'Bip01 L Hand'),
                                          'model': weapon['accessorymodel'], 'slot': 'ebolton_weapon2'})
        if not fight_talent and weapon.get('fightstyle'):
            fs = style_file('fightstyles', weapon['fightstyle'])
            ensure_talent(fs, True)
            ET.SubElement(new, 'talent', {'level': '1', 'name': fs})
        if 'powerstyle' not in out and weapon.get('powerstyle'):
            new.set('powerstyle', style_file('powerstyles', weapon['powerstyle']))
        report['notes'].append(f"{name}: XML1 weapon {weapon['name']} -> BoltOn {weapon['model']} "
                               f"(XML2's stats parser accepts and ignores 'weapon', XMen2.exe 0x4ba383)")
    return sorted_attrs(new)


# ------------------------------------------------------------------ packages
def pkg_entry(f, kind):
    """XML1 .fb manifest entry -> XML2 packagedef child (or None)."""
    stem, ext = os.path.splitext(f)
    if ext in ('.fre', '.ger'):
        return None
    if kind in ('actorskin', 'actoranimdb'):
        s = stem.split('/', 1)[1]
        return kind, copy_actor(s, kind)
    if re.fullmatch(r'(hud/hud_head_|ui/hud/characters/|ui/models/characters/)\d{4}', stem):
        return kind, copy_ui(f)
    if kind == 'fightstyle' and stem.startswith('data/powerstyles/'):
        return kind, 'data/powerstyles/' + style_file('powerstyles', stem.split('/')[-1])
    if kind == 'fightstyle' and stem.startswith('data/fightstyles/'):
        return kind, 'data/fightstyles/' + style_file('fightstyles', stem.split('/')[-1])
    if kind in ('model', 'texture'):
        if f in idx2 or f.replace('.igb', '.igb') in idx2:
            return kind, stem
        # XML1-only model/texture: copy unchanged (IGB format identical)
        emit(stem + '.igb', open(files1[f], 'rb').read())
        return kind, stem
    if kind == 'effect':
        rel = stem[len('effects/'):] if stem.startswith('effects/') else stem
        if f'effects/{rel}.xmlb' in idx2:
            return kind, rel
        src = files1.get(f)
        if src:
            emit(f'Effects/{rel}.XMLB', xmlb.encode(sorted_attrs(parse_x1_text(src))))
            return kind, rel
        report['deferred'].append(f'effect {f} missing')
        return None
    if kind == 'xml':
        if stem + '.xmlb' in idx2:
            return kind, stem
        src = files1.get(f)
        emit(stem.replace('data/', 'Data/', 1) + '.XMLB', xmlb.encode(sorted_attrs(parse_x1_text(src))))
        return kind, stem
    report['deferred'].append(f'package entry kind {kind} {f} not handled')
    return None


def build_packages(name, x2skin):
    lname = name.lower()
    made = []
    for suffix in ('', '_nc'):
        cands = [k for k in man if re.fullmatch(rf'packages/generated/characters/{re.escape(lname)}_\d{{4}}{suffix}\.fb', k)]
        if not cands:
            report['deferred'].append(f'{name}: no XML1 package {suffix or "(combat)"}')
            continue
        # the stats skin's own bundle
        want = [k for k in cands if N.map_skin(re.search(r'_(\d{4})(_nc)?\.fb$', k).group(1)) == x2skin
                or re.search(r'_(\d{4})(_nc)?\.fb$', k).group(1) == x2skin]
        for bundle in (want or cands[:1]):
            old = re.search(r'_(\d{4})(_nc)?\.fb$', bundle).group(1)
            pkg = ET.Element('packagedef')
            seen = set()
            for f, kind in man[bundle]:
                e = pkg_entry(f, kind)
                if e and e not in seen:
                    seen.add(e)
                    ET.SubElement(pkg, e[0], {'filename': e[1]})
            rel = f'Packages/generated/characters/{lname}_{skin_of(old)}{suffix}.PKGB'
            emit(rel, xmlb.encode(pkg))
            made.append(rel)
    return made


def fix_package_for_boltons(pkg_rel, stats_el):
    """XML1 bundles precache weapon models; make sure every BoltOn model is listed (XML2 packages do)."""
    p = os.path.join(OUT, pkg_rel)
    root = xmlb.decode(open(p, 'rb').read())
    have = {(e.tag, e.get('filename')) for e in root}
    changed = False
    for b in stats_el.iter('BoltOn'):
        m = b.get('model')
        entry = ('actorskin', m) if N.is_skin_id(m) else ('model', m)
        if entry not in have:
            ET.SubElement(root, entry[0], {'filename': entry[1]})
            changed = True
    if changed:
        open(p, 'wb').write(xmlb.encode(root))


# ------------------------------------------------------------------ main
def main():
    x1npc = {st.get('name').lower(): st for st in parse_x1_text(f'{X1L}/data/npcstat.eng').iter('stats')}
    names = sorted(x1npc) if args.all_npcs else [n.lower() for n in args.names]
    x2 = {ext: load_xmlb(f'{X2}/Data/npcstat.{ext}') for ext in ('XMLB', 'engb')}
    herostat = load_xmlb(f'{X2}/Data/herostat.engb')
    hero_names = {s.get('name').lower() for s in herostat.iter('stats')}
    drop = {d.strip().lower() for d in args.drop.split(',') if d.strip()}
    keep = {d.strip().lower() for d in args.keep_x2.split(',') if d.strip()}
    holes = {ext: [] for ext in x2}   # additive: new entries take the dropped entries' positions
    for ext, root in x2.items():
        for i, st in reversed(list(enumerate(list(root)))):
            n = st.get('name').lower()
            if (args.mode == 'additive' and n in drop) or (args.mode == 'xml1' and (n not in keep or n in names)):
                root.remove(st)
                if args.mode == 'additive':
                    holes[ext].insert(0, i)
                if ext == 'engb':
                    report['dropped_x2_entries'].append(st.get('name'))
    x2names = {st.get('name').lower() for st in x2['engb']} | hero_names
    converted = []
    for n in names:
        st = x1npc.get(n)
        if st is None:
            raise SystemExit(f'{n} is not an XML1 npcstat entry')
        if n in x2names:
            report['notes'].append(f'{n}: name exists in XML2 - additive mode keeps XML2 entry, XML1 entry skipped')
            continue
        new = convert_stats(st)
        converted.append(new)
        for ext, root in x2.items():
            if holes[ext]:
                root.insert(holes[ext].pop(0), copy.deepcopy(new))
            else:
                root.append(copy.deepcopy(new))
        pk = build_packages(st.get('name'), new.get('skin'))
        for rel in pk:
            fix_package_for_boltons(rel, new)
    for ext, root in x2.items():
        emit(f'Data/npcstat.{ext}', xmlb.encode(root))
    if report['added_talents']:
        emit('Data/shared_talents.XMLB', xmlb.encode(x2_shared_talents))
        emit('Data/shared_talents.engb', xmlb.encode(x2_shared_talents_eng))
    report['converted_entries'] = [xmlb.to_text(copy.deepcopy(c)) for c in converted] if len(converted) < 5 else len(converted)
    report['stats_name_count'] = len({st.get('name').lower() for st in x2['engb']} | hero_names)
    json.dump(report, open(os.path.join(OUT, '_build_report.json'), 'w'), indent=1)
    print(f"variant={args.variant} mode={args.mode}: {len(converted)} entries, {len(report['written'])} files, "
          f"stats names {report['stats_name_count']}/296, talents added {len(report['added_talents'])}, "
          f"deferred {len(report['deferred'])}")


if __name__ == '__main__':
    import shutil
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    main()
