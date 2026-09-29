"""Step 4: non-zone content inventory (UI menus, HUD, fonts, loading screens, conversations, dialogs, subtitles,
data tables, review content, zoneinfo). Writes ui_inventory.json."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, json, os, re, sys

sys.path.insert(0, _REPO + r'/research/sweep')
from sweeplib import parse_text_xml_robust, load_xmlb, walk_files, X1, X1A, X2

SWEEP = _REPO + r'/research/sweep'
EXE2 = open(os.path.join(X2, 'XMen2.exe'), 'rb').read()
EXE1 = open(_REPO + r'/xml1_xbox/default.xbe', 'rb').read()


def in_exe(exe, s):
    return (b'\0' + s.encode('latin-1') + b'\0') in exe or (b'\0' + s.lower().encode('latin-1') + b'\0') in exe


def tagset(root):
    out = collections.Counter()
    for el in root.iter():
        out[el.tag.lower()] += 1
    return out


def attrset(root):
    out = set()
    for el in root.iter():
        for k in el.attrib:
            out.add((el.tag.lower(), k.lower()))
    return out


x2 = walk_files(X2)
x1 = walk_files(X1)
x1a = walk_files(X1A)
inv = {}

# ---------------- menus
menus = {}
x1_menu_types, x2_menu_types = collections.Counter(), collections.Counter()
x1_item_types, x2_item_types = collections.Counter(), collections.Counter()
x1_cmds, x2_cmds = collections.Counter(), collections.Counter()


def cmds_of(root, counter):
    for el in root.iter():
        for k, v in el.attrib.items():
            if k.lower().endswith('cmd') and v.strip():
                for part in v.split(';'):
                    w = part.strip().split(' ')[0].split('(')[0]
                    if w:
                        counter[w.lower()] += 1


for rel, p in sorted(x2.items()):
    if rel.startswith('ui/menus/') and rel.endswith(('.engb', '.xmlb')):
        root = load_xmlb(p)
        x2_menu_types[root.get('type', '')] += 1
        for it in root.iter():
            if it.get('type') and it is not root:
                x2_item_types[it.get('type')] += 1
        cmds_of(root, x2_cmds)
for rel, p in sorted(x1.items()):
    if not rel.startswith('ui/menus/') or not rel.endswith(('.eng', '.xml')):
        continue
    name = rel[9:].rsplit('.', 1)[0]
    root = parse_text_xml_robust(p)
    t = root.get('type', '')
    x1_menu_types[t] += 1
    items = collections.Counter(it.get('type') for it in root.iter() if it is not root and it.get('type'))
    x1_item_types.update(items)
    c = collections.Counter()
    cmds_of(root, c)
    x1_cmds.update(c)
    x2_counterpart = [k for k in x2 if k.startswith('ui/menus/' + name + '.')]
    menus[name] = {'type': t, 'igb': root.get('igb'), 'xml2_has_same_name': bool(x2_counterpart),
                   'type_in_xml2_exe': in_exe(EXE2, t) if t else None,
                   'igb_in_xml2': ('ui/menus/' + (root.get('igb') or '') + '.igb') in x2,
                   'igb_in_xml1': ('ui/menus/' + (root.get('igb') or '') + '.igb') in x1,
                   'commands': sorted(c)}
inv['menus'] = {
    'xml1_menus': menus,
    'xml1_menu_types_missing_in_xml2_exe': sorted(t for t in x1_menu_types if t and not in_exe(EXE2, t)),
    'xml1_item_types_missing_in_xml2_exe': sorted(t for t in x1_item_types if t and not in_exe(EXE2, t)),
    'xml1_commands_missing_in_xml2_exe': sorted(c for c in x1_cmds if not in_exe(EXE2, c)),
    'xml1_menu_types': dict(x1_menu_types), 'xml2_menu_types': dict(x2_menu_types),
    'xml1_menu_count': len(menus),
    'xml2_menu_files': sum(1 for k in x2 if k.startswith('ui/menus/') and k.endswith(('.xmlb', '.engb'))),
}

# ---------------- package/menus bundles (XML1) -> what each menu package loads
man = json.load(open(os.path.join(X1, '_fb_manifest.json')))
inv['menu_packages'] = {b.split('/')[-1][:-3]: len(v) for b, v in man.items()
                        if b.startswith('packages/generated/maps/package/')}

# ---------------- HUD
def listdir_rel(idx, prefix):
    return sorted(k[len(prefix):] for k in idx if k.startswith(prefix))


h1 = listdir_rel(x1, 'hud/')
h2 = listdir_rel(x2, 'hud/')
uh1 = listdir_rel(x1, 'ui/hud/')
uh2 = listdir_rel(x2, 'ui/hud/')
inv['hud'] = {'xml1_hud': len(h1), 'xml2_hud': len(h2), 'same_names': len(set(h1) & set(h2)),
              'xml1_hud_sample': h1[:10], 'xml2_hud_sample': h2[:10],
              'xml1_ui_hud': len(uh1), 'xml2_ui_hud': len(uh2), 'ui_hud_same_names': len(set(uh1) & set(uh2)),
              'hud_head_pattern_xml1_exe': in_exe(EXE1, 'hud/hud_head_%s'),
              'hud_head_pattern_xml2_exe': b'hud_head_%s' in EXE2,
              'ui_hud_characters_pattern_xml2_exe': b'ui/hud/characters/%s' in EXE2}
# ---------------- fonts
f1 = sorted(set(listdir_rel(x1a, 'ui/fonts/')) | set(listdir_rel(x1a, 'textures/fonts/')))
f2 = listdir_rel(x2, 'ui/fonts/')
inv['fonts'] = {'xml1_ui_fonts': listdir_rel(x1a, 'ui/fonts/'), 'xml1_textures_fonts': listdir_rel(x1a, 'textures/fonts/'),
                'xml2_ui_fonts': f2}
# ---------------- loading screens
l1 = listdir_rel(x1a, 'textures/loading/')
l2 = listdir_rel(x2, 'textures/loading/')
zi1 = parse_text_xml_robust(os.path.join(X1, 'data/zoneinfo.eng'))
refs = sorted({z.get('loading') for z in zi1 if z.get('loading')})
inv['loading_screens'] = {
    'xml1_files': len(l1), 'xml2_files': len(l2), 'name_collisions': sorted(set(l1) & set(l2)),
    'xml1_zoneinfo_refs': len(refs),
    'xml1_refs_unresolved': [r for r in refs if (r.lower() + '.igb') not in x1a and (r.lower() + '.igb') not in x2
                             and (r.lower() + '.igb') not in x1]}
# ---------------- zoneinfo
zi2 = load_xmlb(os.path.join(X2, 'Data/zoneinfo.engb'))
inv['zoneinfo'] = {'xml1_entries': len(zi1), 'xml2_entries': len(zi2),
                   'xml1_attrs': sorted({k for z in zi1 for k in z.attrib}),
                   'xml2_attrs': sorted({k for z in zi2 for k in z.attrib}),
                   'xml1_names_use_backslash': sum(1 for z in zi1 if '\\' in z.get('name', '')),
                   'xml1_names_mixed_case': sum(1 for z in zi1 if z.get('name', '') != z.get('name', '').lower())}


# ---------------- conversations / dialogs / subtitles: schema comparison
def schema(files, loader):
    tags, attrs = collections.Counter(), set()
    n = 0
    for p in files:
        try:
            r = loader(p)
        except Exception:
            continue
        n += 1
        tags.update(tagset(r))
        attrs |= attrset(r)
    return n, tags, attrs


def cmp_schema(name, x1files, x2files):
    n1, t1, a1 = schema(x1files, parse_text_xml_robust)
    n2, t2, a2 = schema(x2files, load_xmlb)
    return {'xml1_files': n1, 'xml2_files': n2,
            'xml1_tags': dict(t1.most_common()), 'xml2_tags': dict(t2.most_common()),
            'xml1_only_tags': sorted(set(t1) - set(t2)), 'xml2_only_tags': sorted(set(t2) - set(t1)),
            'xml1_only_attrs': sorted('%s.%s' % x for x in a1 - a2)[:80],
            'xml2_only_attrs': sorted('%s.%s' % x for x in a2 - a1)[:80]}


def files(idx, prefix, exts):
    return [p for k, p in idx.items() if k.startswith(prefix) and k.endswith(exts)]


inv['conversations'] = cmp_schema('conversations', files(x1, 'conversations/', ('.eng',)),
                                  files(x2, 'conversations/', ('.engb',)))
inv['dialogs'] = cmp_schema('dialogs', files(x1, 'dialogs/', ('.eng',)), files(x2, 'dialogs/', ('.engb',)))
inv['subtitles'] = cmp_schema('subtitles', files(x1, 'subtitles/', ('.eng',)), files(x2, 'subtitles/', ('.engb',)))
inv['movie_subtitles'] = cmp_schema('movie_subtitles', files(x1a, 'movies/', ('.eng',)), files(x2, 'movies/', ('.engb',)))
inv['missions'] = cmp_schema('missions', files(x1a, 'data/missions/', ('.eng', '.xml')),
                             files(x2, 'data/missions/', ('.engb',)))
inv['personal'] = cmp_schema('personal', files(x1a, 'data/personal/', ('.eng',)), files(x2, 'data/personal/', ('.engb',)))
# conversations: XML2 uses @TOKEN@ strings in XMLB and english in engb; XML1 uses literal text + %X-TEAM% style markers
tok = collections.Counter()
for p in files(x1, 'conversations/', ('.eng',)):
    tok.update(re.findall(r'%[A-Z_\-]+%', open(p, encoding='latin-1').read()))
inv['conversations']['xml1_text_markers'] = dict(tok.most_common(20))
# ---------------- data tables in XML1 not in XML2 and vice versa
d1 = {os.path.splitext(k[5:])[0] for k in list(x1) + list(x1a) if k.startswith('data/') and k.count('/') == 1}
d2 = {os.path.splitext(k[5:])[0] for k in x2 if k.startswith('data/') and k.count('/') == 1}
inv['data_tables'] = {'xml1_only': sorted(d1 - d2), 'xml2_only': sorted(d2 - d1), 'both': sorted(d1 & d2)}
# review content
inv['review'] = {'xml1_comic': listdir_rel(x1a, 'textures/comic/'), 'xml1_concept': len(listdir_rel(x1a, 'textures/concept/')),
                 'xml1_personal_textures': len(listdir_rel(x1a, 'textures/personal/')),
                 'xml2_comic': len(listdir_rel(x2, 'textures/comic/')),
                 'xml2_concept': len(listdir_rel(x2, 'textures/concept/'))}
json.dump(inv, open(os.path.join(SWEEP, 'ui_inventory.json'), 'w'), indent=1, sort_keys=True)
m = inv['menus']
print('menus: xml1', m['xml1_menu_count'], 'xml2 files', m['xml2_menu_files'])
print('  xml1 menu types', m['xml1_menu_types'])
print('  types missing in xml2 exe', m['xml1_menu_types_missing_in_xml2_exe'])
print('  item types missing in xml2 exe', m['xml1_item_types_missing_in_xml2_exe'])
print('  commands missing in xml2 exe', m['xml1_commands_missing_in_xml2_exe'])
print('  no same-name xml2 menu:', sorted(k for k, v in m['xml1_menus'].items() if not v['xml2_has_same_name']))
print('hud', inv['hud'])
print('fonts xml1', len(inv['fonts']['xml1_ui_fonts']), len(inv['fonts']['xml1_textures_fonts']), 'xml2', len(inv['fonts']['xml2_ui_fonts']))
print('   ', inv['fonts']['xml1_ui_fonts'][:12], inv['fonts']['xml2_ui_fonts'][:12])
print('loading', {k: v if not isinstance(v, list) else (len(v), v[:8]) for k, v in inv['loading_screens'].items()})
print('zoneinfo', inv['zoneinfo'])
for k in ('conversations', 'dialogs', 'subtitles', 'movie_subtitles', 'missions', 'personal'):
    v = inv[k]
    print(k, v['xml1_files'], v['xml2_files'], 'x1-only tags', v['xml1_only_tags'], 'x2-only tags', v['xml2_only_tags'])
    print('    x1-only attrs', v['xml1_only_attrs'][:30])
print('conv markers', inv['conversations']['xml1_text_markers'])
print('data tables', inv['data_tables'])
print('review', inv['review'])
