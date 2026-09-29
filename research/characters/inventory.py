"""Full inventory of every XML1 character (herostat + npcstat) and what it needs to run in XML2.

Outputs inventory_characters.json (one record per stats entry) and inventory_characters.tsv (summary).
Every file reference is resolved against xml1_loose (source) and the XML2 install (collision/sharing).
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, csv, json, os, re
from common import *
import x1names as N

idx2 = x2_index()
files1 = x1_files()
man = manifest()
col = json.load(open(os.path.join(HERE, 'collisions.json')))
status_of = {}
for cat, d in col.items():
    for st, lst in d.items():
        for rel in lst:
            status_of[rel] = st

COSTUMES_X2 = {'astonishing', 'aoa', '60s', '70s', 'weaponx', 'future', 'winter', 'civilian'}

# XML2 reference sets
x2stats = {}
for f in ('herostat', 'npcstat'):
    for st in load_xmlb(f'{X2}/Data/{f}.engb').iter('stats'):
        x2stats[st.get('name').lower()] = (f, st)
x2_shared_talents = {t.get('name').lower() for t in load_xmlb(f'{X2}/Data/shared_talents.XMLB').iter('talent')}
x2_talent_files = {os.path.splitext(os.path.basename(p))[0].lower() for p in idx2 if p.startswith('data/talents/')}
x2_hero_talents = set()
for p in idx2:
    if p.startswith('data/talents/') and p.endswith('.xmlb'):
        x2_hero_talents |= {t.get('name').lower() for t in load_xmlb(idx2[p]).iter('talent')}
x1_shared_talents = {t.get('name').lower() for t in parse_x1_text(f'{X1L}/data/shared_talents.eng').iter() if t.tag.lower() == 'talent'}
x1_weapons = {w.get('name').lower(): dict(w.attrib) for w in parse_x1_text(f'{X1L}/data/weapons/weapons.eng').iter('weapon')}
x2_sounds = {os.path.splitext(os.path.basename(p))[0].lower() for p in idx2 if p.startswith('sounds/eng/')}
x1_sounds = set()
for d, _, fs in os.walk(_REPO + '/xml1_xbox/sounds/zsds'):
    for f in fs:
        x1_sounds.add(os.path.splitext(f)[0].lower())


def fstat(rel):
    """status of an XML1 logical file path (with extension)."""
    if rel not in files1:
        return 'MISSING_IN_XML1'
    return status_of.get(rel, '?')


def textfile(stem):
    for e in ('.eng', '.xml'):
        if stem + e in files1:
            return stem + e
    return None


def skins_of(st):
    base = st.get('skin') or ''
    out = {'default': base}
    if N.is_skin_id(base):
        pre = base[:-2]
        for k, v in st.attrib.items():
            if k.lower().startswith('skin_') and v.isdigit():
                out[k.lower()[5:]] = pre + v.zfill(2)
    return out


records = []
for fname in ('herostat', 'npcstat'):
    for st in parse_x1_text(f'{X1L}/data/{fname}.eng').iter('stats'):
        a = {k.lower(): v for k, v in st.attrib.items()}
        name = a.get('name', '')
        r = {'file': fname, 'name': name, 'team': a.get('team'), 'playable': a.get('playable'),
             'charactername': a.get('charactername'), 'name_in_xml2': name.lower() in x2stats}
        sk = skins_of(st)
        r['skins'] = {c: {'x1': s, 'xml2_name': N.map_skin(s) if N.is_skin_id(s) else s,
                          'actor': fstat(f'actors/{s}.igb'),
                          'hud_head': fstat(f'hud/hud_head_{s}.igb') if f'hud/hud_head_{s}.igb' in files1 else None,
                          'ui_hud': fstat(f'ui/hud/characters/{s}.igb') if f'ui/hud/characters/{s}.igb' in files1 else None,
                          'ui_models': fstat(f'ui/models/characters/{s}.igb') if f'ui/models/characters/{s}.igb' in files1 else None}
                      for c, s in sk.items()}
        r['costumes_not_in_xml2'] = [c for c in sk if c != 'default' and c not in COSTUMES_X2]
        ca = a.get('characteranims')
        r['characteranims'] = {'x1': ca, 'xml2_name': N.map_animdb(ca) if ca else None,
                               'status': fstat(f'actors/{ca}.igb') if ca else None}
        ps = a.get('powerstyle')
        psf = textfile(f'data/powerstyles/{ps}') if ps else None
        r['powerstyle'] = {'x1': ps, 'file': psf, 'status': fstat(psf) if psf else ('MISSING_IN_XML1' if ps else None),
                           'xml2_name': N.map_powerstyle(ps)}
        ms = a.get('moveset1')
        msf = textfile(f'data/fightstyles/{ms}') if ms else None
        r['moveset1'] = {'x1': ms, 'file': msf, 'status': fstat(msf) if msf else ('MISSING_IN_XML1' if ms else None)}
        # talents / fightstyles
        tal = []
        for t in st:
            if t.tag.lower() != 'talent':
                continue
            tn = (t.get('name') or '').lower()
            inline = any(k.lower() in ('descname', 'description', 'power') for k in t.attrib) or len(t) > 0
            where = ('xml2_shared' if tn in x2_shared_talents else
                     'xml2_hero_file' if tn in x2_hero_talents else
                     'x1_inline_def' if inline else
                     'x1_shared_only' if tn in x1_shared_talents else 'UNDEFINED')
            fs = None
            if tn.startswith(('fightstyle_', 'moveset_')):
                f = textfile(f'data/fightstyles/{tn}')
                fs = {'file': f, 'status': fstat(f) if f else 'MISSING_IN_XML1', 'xml2_name': N.map_fightstyle(tn)}
            tal.append({'name': tn, 'level': t.get('level'), 'defined': where, 'fightstyle': fs})
        r['talents'] = tal
        r['races'] = [c.get('name') for c in st if c.tag.lower() == 'race']
        # weapon -> bolt-on
        wp = a.get('weapon')
        if wp:
            w = x1_weapons.get(wp.lower())
            r['weapon'] = {'x1': wp, 'def': w,
                           'model_status': fstat(w['model'].lower() + '.igb') if w and w.get('model') else None,
                           'fightstyle': w.get('fightstyle') if w else None, 'powerstyle': w.get('powerstyle') if w else None}
        else:
            r['weapon'] = None
        r['boltons'] = [{k.lower(): v for k, v in b.attrib.items()} for b in st if b.tag.lower() == 'bolton']
        for b in r['boltons']:
            m = b.get('model', '')
            b['model_status'] = fstat(f'actors/{m}.igb') if N.is_skin_id(m) else fstat(m.lower() + '.igb')
            if b.get('anim'):
                b['anim_status'] = fstat(f"actors/{b['anim']}.igb")
        r['multipart'] = [{k.lower(): v for k, v in b.attrib.items()} for b in st if b.tag.lower() == 'multipart']
        r['activepowerups'] = sum(1 for c in st.iter() if c.tag.lower() == 'activepowerup')
        sd = a.get('sounddir')
        r['sounddir'] = {'x1': sd, 'x1_bank': (sd or '').lower() in x1_sounds if sd else None,
                         'xml2_has_same_name': (sd or '').lower() in x2_sounds if sd else None}
        # XML1 packages for this name
        pk = sorted(k for k in man if re.fullmatch(rf'packages/generated/characters/{re.escape(name.lower())}_(\d+|xml)(_nc)?\.fb', k))
        r['x1_packages'] = pk
        r['x1_package_files'] = sorted({f for k in pk for f, kind in man[k]})
        r['xml1_only_attrs'] = sorted(k for k in a if k in ('leader', 'ratingmelee', 'ratingranged', 'ratingsupport',
                                                           'ratingdurability', 'throwally', 'weapon'))
        records.append(r)

json.dump(records, open(os.path.join(HERE, 'inventory_characters.json'), 'w'), indent=1)
with open(os.path.join(HERE, 'inventory_characters.tsv'), 'w', newline='') as fh:
    w = csv.writer(fh, delimiter='\t')
    w.writerow(['file', 'name', 'name_in_xml2', 'team', 'skin', 'skin_xml2', 'skins_all', 'skin_actor_status',
                'characteranims', 'anims_status', 'anims_xml2', 'powerstyle', 'ps_status', 'ps_xml2', 'moveset1',
                'talents', 'undefined_talents', 'weapon', 'sounddir', 'x1_bank', 'xml2_bank_same_name', 'packages'])
    for r in records:
        d = r['skins'].get('default', {})
        w.writerow([r['file'], r['name'], r['name_in_xml2'], r['team'], d.get('x1'), d.get('xml2_name'),
                    ' '.join(f"{c}:{v['x1']}" for c, v in r['skins'].items()), d.get('actor'),
                    r['characteranims']['x1'], r['characteranims']['status'], r['characteranims']['xml2_name'],
                    r['powerstyle']['x1'], r['powerstyle']['status'], r['powerstyle']['xml2_name'],
                    r['moveset1']['x1'], ' '.join(t['name'] for t in r['talents']),
                    ' '.join(t['name'] for t in r['talents'] if t['defined'] in ('UNDEFINED', 'x1_shared_only')),
                    r['weapon']['x1'] if r['weapon'] else '', r['sounddir']['x1'], r['sounddir']['x1_bank'],
                    r['sounddir']['xml2_has_same_name'], len(r['x1_packages'])])

# ---- summary
c = collections.Counter()
for r in records:
    c['entries'] += 1
    c['heroes' if r['file'] == 'herostat' else 'npcs'] += 1
    if r['name_in_xml2']:
        c['name_collides_with_xml2'] += 1
    d = r['skins'].get('default', {})
    c['skin_actor:' + str(d.get('actor'))] += 1
    c['anims:' + str(r['characteranims']['status'])] += 1
    c['powerstyle:' + str(r['powerstyle']['status'])] += 1
    if r['weapon']:
        c['has_weapon'] += 1
    for t in r['talents']:
        c['talent_def:' + t['defined']] += 1
    if r['sounddir']['x1']:
        c['sounddir_set'] += 1
        c['sounddir_x1_bank_exists:' + str(r['sounddir']['x1_bank'])] += 1
        c['sounddir_name_also_in_xml2:' + str(r['sounddir']['xml2_has_same_name'])] += 1
    if not r['x1_packages']:
        c['no_x1_package'] += 1
    if r['costumes_not_in_xml2']:
        c['costume_not_in_xml2'] += 1
for k in sorted(c):
    print(f'{k:45} {c[k]}')
und = collections.Counter(t['name'] for r in records for t in r['talents'] if t['defined'] in ('UNDEFINED', 'x1_shared_only'))
print('talents referenced by XML1 stats but not defined in XML2 (name: uses):', dict(und))
print('distinct skins:', len({v['x1'] for r in records for v in r['skins'].values()}),
      ' distinct anim dbs:', len({r['characteranims']['x1'] for r in records if r['characteranims']['x1']}),
      ' distinct powerstyles:', len({r['powerstyle']['x1'] for r in records if r['powerstyle']['x1']}),
      ' distinct sounddirs:', len({r['sounddir']['x1'] for r in records if r['sounddir']['x1']}))
