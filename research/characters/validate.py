"""Offline validation of a build_chars.py output tree (overlay on the XML2 install).

usage: python validate.py <out_dir>
Checks
  1. every XMLB-family output decodes, re-encodes byte-identically, and has lowercase + sorted attribute
     names on every element (XML2 attribute lookup is a binary search)
  2. herostat+npcstat: unique names (case-insensitive) <= 296 (XMen2.exe 0x44c1a7), herostat <= 21
     (0x44bab0 loop bound 0x15); names <= 31 chars (strncpy 0x20, 0x4b9c40); skins 4-5 digits with
     prefix <= 255 (byte, 0x4b9c40)
  3. for every stats entry that is new/changed vs XML2: skin actor, characteranims, BoltOn models/anims,
     powerstyle, moveset, fightstyle talents, talents defined in shared_talents, sounddir bank, and the
     generated/characters/<name>_<skin>[_nc] packages exist in output-or-XML2
  4. every package entry resolves to a file in output-or-XML2
  5. output files never replace an XML2 file except the intended data overrides
  6. renamed skin IGBs: same size as the XML1 source, contain '<new>' and no bare '<old>' object name
"""
import os, re, struct, sys
from common import *
import x1names as N

OUT = sys.argv[1]
idx2 = x2_index()
out = {}
for d, _, fs in os.walk(OUT):
    for f in fs:
        if f.startswith('_'):
            continue
        p = os.path.join(d, f)
        out[os.path.relpath(p, OUT).replace(os.sep, '/').lower()] = p
errors, warns = [], []
ALLOWED_OVERRIDES = {'data/npcstat.xmlb', 'data/npcstat.engb', 'data/herostat.xmlb', 'data/herostat.engb',
                     'data/shared_talents.xmlb', 'data/shared_talents.engb'}


def exists(rel):
    r = rel.lower().replace('\\', '/')
    return r in out or r in idx2


def load(rel_l):
    p = out.get(rel_l) or idx2.get(rel_l)
    return load_xmlb(p)


# 1. encoding
for rel, p in out.items():
    if rel.endswith(('.xmlb', '.engb', '.pkgb', '.chrb', '.navb', '.boyb')):
        data = open(p, 'rb').read()
        try:
            root = xmlb.decode(data)
        except Exception as e:
            errors.append(f'{rel}: does not decode: {e}')
            continue
        if xmlb.encode(root) != data:
            errors.append(f'{rel}: re-encode differs')
        for el in root.iter():
            keys = list(el.attrib)
            if any(k != k.lower() for k in keys):
                errors.append(f'{rel}: <{el.tag}> has non-lowercase attribute {keys}')
            if keys != sorted(keys):
                errors.append(f'{rel}: <{el.tag}> attributes not sorted {keys}')
# 5. overrides
for rel in out:
    if rel in idx2 and rel not in ALLOWED_OVERRIDES:
        errors.append(f'{rel}: would overwrite an XML2 file')

# 2. stats tables
stats = {}
for f in ('herostat', 'npcstat'):
    for ext in ('xmlb', 'engb'):
        root = load(f'data/{f}.{ext}')
        names = [st.get('name') for st in root.iter('stats')]
        stats[(f, ext)] = {st.get('name').lower(): st for st in root.iter('stats')}
        if len({n.lower() for n in names}) != len(names):
            errors.append(f'data/{f}.{ext}: duplicate names')
for ext in ('xmlb', 'engb'):
    allnames = set(stats[('herostat', ext)]) | set(stats[('npcstat', ext)])
    n_total = len(stats[('herostat', ext)]) + len(stats[('npcstat', ext)])
    if n_total != len(allnames):
        errors.append(f'{ext}: a name is in both herostat and npcstat')
    if len(allnames) > 296:
        errors.append(f'{ext}: {len(allnames)} stats names > 296-slot table')
    if len(stats[('herostat', ext)]) > 21:
        errors.append(f'{ext}: herostat has {len(stats[("herostat", ext)])} > 21 entries')
if set(stats[('npcstat', 'xmlb')]) != set(stats[('npcstat', 'engb')]):
    errors.append('npcstat.XMLB and npcstat.engb list different names')

x2orig = {}
for f in ('herostat', 'npcstat'):
    for st in load_xmlb(idx2[f'data/{f}.engb']).iter('stats'):
        x2orig[st.get('name').lower()] = xmlb.to_text(st)
talents = {t.get('name').lower() for t in load('data/shared_talents.xmlb').iter('talent')}
talents_eng = {t.get('name').lower() for t in load('data/shared_talents.engb').iter('talent')}
if talents != talents_eng:
    errors.append('shared_talents XMLB/engb differ')
hero_talents = set()
for rel in idx2:
    if rel.startswith('data/talents/') and rel.endswith('.xmlb'):
        hero_talents |= {t.get('name').lower() for t in load_xmlb(idx2[rel]).iter('talent')}
if len(talents) > 99:
    errors.append(f'shared_talents has {len(talents)} > 99 talents (XMen2.exe 0x4c05d0 id range 0..98)')

new_entries = []
for (f, ext), d in stats.items():
    if ext != 'engb':
        continue
    for n, st in d.items():
        if n not in x2orig or xmlb.to_text(st) != x2orig[n]:
            new_entries.append((f, st))
banks = {os.path.splitext(os.path.basename(p))[0].lower() for p in list(idx2) + list(out) if p.startswith('sounds/eng/')}
checked_pkgs = set()
for f, st in new_entries:
    name = st.get('name')
    where = f'{f}:{name}'
    if len(name) > 31:
        errors.append(f'{where}: name longer than 31 chars')
    skin = st.get('skin', '')
    if not re.fullmatch(r'\d{4,5}', skin) or int(skin[:-2]) > 255:
        errors.append(f'{where}: skin {skin!r} not 4-5 digits with prefix<=255')
    else:
        if int(skin[:-2]) >= 140 and int(skin[:-2]) != 200 and f'actors/{skin}.igb' in idx2:
            errors.append(f'{where}: skin {skin} is in the XML1 range but XML2 has that file')
    if not exists(f'actors/{skin}.igb'):
        errors.append(f'{where}: actors/{skin}.igb missing')
    for k, v in st.attrib.items():
        if k.startswith('skin_') and not exists(f'actors/{skin[:-2]}{v.zfill(2)}.igb'):
            warns.append(f'{where}: costume {k} -> actors/{skin[:-2]}{v.zfill(2)}.igb missing')
    ca = st.get('characteranims')
    if ca and not exists(f'actors/{ca}.igb'):
        errors.append(f'{where}: characteranims actors/{ca}.igb missing')
    ps = st.get('powerstyle')
    if ps and not exists(f'data/powerstyles/{ps}.xmlb'):
        errors.append(f'{where}: powerstyle data/powerstyles/{ps} missing')
    ms = st.get('moveset1')
    if ms and not exists(f'data/fightstyles/{ms}.xmlb'):
        errors.append(f'{where}: moveset1 data/fightstyles/{ms} missing')
    sd = st.get('sounddir')
    if sd and sd.lower() not in banks:
        errors.append(f'{where}: sounddir {sd} has no bank')
    for c in st:
        if c.tag == 'talent':
            tn = c.get('name').lower()
            if tn not in talents and tn not in hero_talents:
                errors.append(f'{where}: talent {tn} not defined in shared_talents')
            if tn.startswith('fightstyle_') and not exists(f'data/fightstyles/{tn}.xmlb'):
                errors.append(f'{where}: fightstyle data/fightstyles/{tn} missing')
        if c.tag == 'BoltOn':
            m = c.get('model', '')
            ok = exists(f'actors/{m}.igb') if N.is_skin_id(m) else exists(m + '.igb')
            if not ok:
                errors.append(f'{where}: BoltOn model {m} missing')
            if c.get('anim') and not exists(f"actors/{c.get('anim')}.igb"):
                errors.append(f"{where}: BoltOn anim {c.get('anim')} missing")
    if f == 'npcstat':
        for suffix in ('', '_nc'):
            pk = f'packages/generated/characters/{name.lower()}_{skin}{suffix}.pkgb'
            if not exists(pk):
                errors.append(f'{where}: package {pk} missing')
            else:
                checked_pkgs.add(pk)

# 4. package entries
KIND = {'actorskin': lambda v: f'actors/{v}.igb', 'actoranimdb': lambda v: f'actors/{v}.igb',
        'model': lambda v: v + '.igb', 'texture': lambda v: v + '.igb', 'effect': lambda v: f'effects/{v}.xmlb',
        'fightstyle': lambda v: v + '.xmlb', 'xml': lambda v: v + '.xmlb', 'xml_resident': lambda v: v + '.xmlb'}
for rel in sorted(set(r for r in out if r.endswith('.pkgb')) | checked_pkgs):
    for e in load(rel):
        fn = e.get('filename')
        path = KIND.get(e.tag, lambda v: None)(fn.replace('actors/', '') if e.tag.startswith('actor') else fn)
        if path is None:
            warns.append(f'{rel}: entry kind {e.tag} not checked')
        elif not exists(path):
            errors.append(f'{rel}: <{e.tag} filename="{fn}"> -> {path} missing')

# 6. renamed IGBs
files1 = x1_files()
for rel, p in out.items():
    m = re.fullmatch(r'(actors/|ui/hud/characters/|ui/models/characters/|hud/hud_head_)(\d{5})\.igb', rel)
    if not m:
        continue
    new = m.group(2)
    old = str(int(new) - N.SKIN_OFFSET).zfill(4)
    src = files1.get(f'{m.group(1)}{old}.igb')
    if not src:
        continue
    a, b = open(src, 'rb').read(), open(p, 'rb').read()
    if len(a) != len(b):
        errors.append(f'{rel}: size differs from XML1 source')
    olds = len(re.findall(rb'[\x00-\x20]' + old.encode() + rb'(?:_outline|_skel)?\x00', b))
    news = len(re.findall(re.escape(new.encode()) + rb'(?:_outline|_skel)?\x00', b))
    if olds:
        errors.append(f'{rel}: still contains {olds} bare "{old}" object names')
    if not news and re.search(re.escape(old.encode()) + rb'\x00', a):
        errors.append(f'{rel}: new name {new} not present')
    diff = sum(x != y for x, y in zip(a, b))
    warns.append(f'{rel}: {news} names renamed, {diff} bytes changed (in-place)') if diff else None

print(f'validated {OUT}: {len(out)} files, {len(new_entries)} new/changed stats entries, '
      f'{len(checked_pkgs)} character packages')
for w in warns:
    print('  note:', w)
for e in errors:
    print('  ERROR:', e)
print('RESULT:', 'PASS' if not errors else f'FAIL ({len(errors)} errors)')
sys.exit(1 if errors else 0)
