"""Emit x1_namespace_map.json: the complete old->new name table produced by x1names for every XML1
character asset, so zone/script/package converters can rewrite references without importing x1names.
Also asserts the scheme is collision-free against the XML2 install."""
import json, os, re
from common import *
import x1names as N

files = x1_files()
idx2 = x2_index()
m = {'skins': {}, 'animdbs': {}, 'powerstyles': {}, 'fightstyles': {}, 'stats_names_shared_with_xml2': [],
     'rules': N.__doc__}
for rel in files:
    mm = re.fullmatch(r'(?:actors/|hud/hud_head_|ui/(?:hud|models)/characters/)(\d{4})\.igb', rel)
    if mm:
        m['skins'][mm.group(1)] = N.map_skin(mm.group(1))
    mm = re.fullmatch(r'actors/([^/]+)\.igb', rel)
    if mm and not N.is_skin_id(mm.group(1)):
        m['animdbs'][mm.group(1)] = N.map_animdb(mm.group(1))
    mm = re.fullmatch(r'data/powerstyles/([^/]+)\.(eng|xml)', rel)
    if mm:
        m['powerstyles'][mm.group(1)] = N.map_powerstyle(mm.group(1))
    mm = re.fullmatch(r'data/fightstyles/([^/]+)\.(eng|xml)', rel)
    if mm:
        m['fightstyles'][mm.group(1)] = N.map_fightstyle(mm.group(1))
for f in ('herostat', 'npcstat'):
    x2n = {st.get('name').lower() for g in ('herostat', 'npcstat') for st in load_xmlb(f'{X2}/Data/{g}.engb').iter('stats')}
    for st in parse_x1_text(f'{X1L}/data/{f}.eng').iter('stats'):
        if st.get('name').lower() in x2n:
            m['stats_names_shared_with_xml2'].append(st.get('name'))
# collision-freedom checks
errs = []
for old, new in m['skins'].items():
    for pat in ('actors/{}.igb', 'hud/hud_head_{}.igb', 'ui/hud/characters/{}.igb', 'ui/models/characters/{}.igb'):
        if pat.format(new) in idx2:
            errs.append(f'skin {old}->{new}: {pat.format(new)} exists in XML2')
    if int(new[:-2]) > 255:
        errs.append(f'skin {new}: prefix > 255')
for old, new in m['animdbs'].items():
    if new != old and f'actors/{new.lower()}.igb' in idx2:
        errs.append(f'animdb {old}->{new} exists in XML2')
    if new == old and f'actors/{old.lower()}.igb' in idx2 and not N.shares_xml2_animdb(old):
        errs.append(f'animdb {old} collides and is not renamed')
for old, new in m['powerstyles'].items():
    if new != old and f'data/powerstyles/{new.lower()}.xmlb' in idx2:
        errs.append(f'powerstyle {old}->{new} exists in XML2')
m['check_errors'] = errs
json.dump(m, open(os.path.join(HERE, 'x1_namespace_map.json'), 'w'), indent=1, sort_keys=True)
print(f"skins {len(m['skins'])}, animdbs {len(m['animdbs'])} ({sum(o != n for o, n in m['animdbs'].items())} renamed), "
      f"powerstyles {len(m['powerstyles'])} ({sum(o != n for o, n in m['powerstyles'].items())} renamed), "
      f"fightstyles {len(m['fightstyles'])}, stats names shared {len(m['stats_names_shared_with_xml2'])}; "
      f"collision errors: {len(errs)}")
for e in errs:
    print('  ', e)
