"""Aggregate per-zone sweep results: characters, sound banks, script functions, missing refs, skins."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, json, os, re, sys

sys.path.insert(0, _REPO + r'/research/sweep')
from sweeplib import parse_text_xml_robust, load_xmlb, walk_files, X1, X1A, X2

SWEEP = _REPO + r'/research/sweep'
zones = json.load(open(os.path.join(SWEEP, 'zones.json')))
graph = json.load(open(os.path.join(SWEEP, 'graph.json')))
reach = set(graph['reachable_from_new_game'])
manifest = json.load(open(os.path.join(X1, '_fb_manifest.json')))


def stats_names(root):
    return {e.get('name').lower(): e for e in root.iter('stats') if e.get('name')}


x1_npc = stats_names(parse_text_xml_robust(os.path.join(X1, 'data/npcstat.eng')))
x1_hero = stats_names(parse_text_xml_robust(os.path.join(X1, 'data/herostat.eng')))
x2_npc = stats_names(load_xmlb(os.path.join(X2, 'Data/npcstat.engb')))
x2_hero = stats_names(load_xmlb(os.path.join(X2, 'Data/herostat.engb')))
char_pkgs1 = {b.split('/')[-1][:-3].lower() for b in manifest if b.startswith('packages/generated/characters/')}
char_pkgs2 = {f.lower().rsplit('.', 1)[0] for f in os.listdir(os.path.join(X2, 'Packages/generated/characters'))}

# ---------------- characters
need = collections.defaultdict(set)
for z, r in zones.items():
    for c in r.get('chr_characters', []) + r.get('spawner_characters', []):
        need[c.lower()].add(z)
chars = {}
for c, zs in sorted(need.items()):
    s1 = x1_npc.get(c) or x1_hero.get(c)
    s2 = x2_npc.get(c) or x2_hero.get(c)
    skin1 = s1.get('skin') if s1 is not None else None
    skin2 = s2.get('skin') if s2 is not None else None
    chars[c] = {
        'zones': len(zs), 'reachable_zones': len(zs & reach),
        'in_xml1_stats': 'npcstat' if c in x1_npc else ('herostat' if c in x1_hero else None),
        'in_xml2_stats': 'npcstat' if c in x2_npc else ('herostat' if c in x2_hero else None),
        'xml1_skin': skin1, 'xml2_skin': skin2,
        'xml1_package': (c + '_' + skin1) in char_pkgs1 if skin1 else None,
        'xml1_characteranims': s1.get('characteranims') if s1 is not None else None,
        'xml2_characteranims': s2.get('characteranims') if s2 is not None else None,
    }
cstat = collections.Counter()
for c, d in chars.items():
    cstat['x1:%s x2:%s' % (bool(d['in_xml1_stats']), bool(d['in_xml2_stats']))] += 1

# ---------------- skins / actors collision + free numbers
x2_actors = {f.lower().rsplit('.', 1)[0] for f in os.listdir(os.path.join(X2, 'Actors'))}
x1_actors = {f.lower().rsplit('.', 1)[0] for f in os.listdir(os.path.join(X1, 'actors'))}
x2_skinnums = sorted(int(a) for a in x2_actors if a.isdigit())
x1_skinnums = sorted(int(a) for a in x1_actors if a.isdigit())
coll_actor = sorted(x1_actors & x2_actors)
# candidate remap: XML1 skin NNMM -> 7NNMM style 5-digit, check none used
for prefix in range(1, 10):
    cand = {int('%d%04d' % (prefix, n)) for n in x1_skinnums}
    if not cand & set(x2_skinnums) and not cand & set(x1_skinnums):
        free_prefix = prefix
        break
else:
    free_prefix = None
# stats skin references in XML2 (5-digit?)
x2_stat_skins = sorted({e.get('skin') for e in list(x2_npc.values()) + list(x2_hero.values()) if e.get('skin')})

# ---------------- sound banks
def banks(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            m = re.match(r'(.+)_([acdmv])\.(zss|zsm)$', f, re.I)
            if m:
                out.setdefault(m.group(1).lower(), set()).add(m.group(2).lower())
            elif f.lower().endswith(('.zss', '.zsm')):
                out.setdefault(f.lower().rsplit('.', 1)[0], set()).add('*')
    return out


b1 = banks(_REPO + r'/xml1_xbox/sounds')
b2 = banks(os.path.join(X2, 'Sounds'))
soundfiles = collections.defaultdict(set)
music = collections.defaultdict(set)
sprefix = collections.Counter()
for z, r in zones.items():
    s = r.get('sounds') or {}
    if s.get('soundfile'):
        soundfiles[s['soundfile'].lower()].add(z)
    for m in s.get('music', []):
        music[m.lower()].add(z)
    for k, v in (s.get('ref_prefixes') or {}).items():
        sprefix[k] += v
bank_need = {b: {'zones': len(zs), 'reachable': len(zs & reach), 'in_xml1': b in b1, 'in_xml2': b in b2,
                 'xml1_parts': sorted(b1.get(b, [])), 'xml2_parts': sorted(b2.get(b, []))}
             for b, zs in sorted(soundfiles.items())}

# ---------------- scripts
miss_fn = collections.Counter()
miss_fn_zones = collections.Counter()
sig_fn = collections.Counter()
not_crlf = set()
for z, r in zones.items():
    sc = r.get('scripts') or {}
    for k, n in (sc.get('missing_in_xml2') or {}).items():
        miss_fn[k] += n
        miss_fn_zones[k] += 1
    for k in (sc.get('signature_changed') or {}):
        sig_fn[k] += 1
    not_crlf.update(sc.get('not_crlf', []))
zones_needing_fn = sum(1 for r in zones.values() if (r.get('scripts') or {}).get('missing_in_xml2'))
# ---------------- missing refs
miss_ref = collections.defaultdict(set)
status_tot = collections.Counter()
for z, r in zones.items():
    for k, v in (r.get('refs_missing') or {}).items():
        for x in v:
            miss_ref[k].add(x)
    for k, v in (r.get('refs_status_counts') or {}).items():
        status_tot[k] += v
kept = collections.Counter()
for r in zones.values():
    for k in r.get('kept_xml2', []):
        kept[k] += 1
bundle_missing = sorted({m for r in zones.values() for m in r.get('missing_bundle_files', [])})

agg = {
    'characters': {'summary': dict(cstat), 'total': len(chars), 'detail': chars},
    'actors': {'xml1_actor_files': len(x1_actors), 'xml2_actor_files': len(x2_actors),
               'name_collisions': len(coll_actor), 'collisions': coll_actor,
               'xml1_skin_numbers': len(x1_skinnums), 'xml2_skin_numbers': len(x2_skinnums),
               'xml2_skin_range': [x2_skinnums[0], x2_skinnums[-1]] if x2_skinnums else None,
               'free_5digit_prefix_for_xml1_skins': free_prefix},
    'sound_banks': {'xml1_banks': len(b1), 'xml2_banks': len(b2), 'name_collisions': sorted(set(b1) & set(b2)),
                    'zone_soundfiles': bank_need, 'music_refs': {k: len(v) for k, v in sorted(music.items())},
                    'sound_ref_prefixes': dict(sprefix.most_common())},
    'scripts': {'missing_functions_calls': dict(miss_fn.most_common()),
                'missing_functions_zone_count': dict(miss_fn_zones.most_common()),
                'zones_using_missing_functions': zones_needing_fn,
                'signature_changed_zone_count': dict(sig_fn), 'not_crlf_files': sorted(not_crlf)},
    'refs': {'status_totals': dict(status_tot), 'missing': {k: sorted(v) for k, v in miss_ref.items()},
             'bundle_listed_but_absent': bundle_missing},
    'kept_xml2_versions': dict(kept.most_common()),
}
json.dump(agg, open(os.path.join(SWEEP, 'aggregate.json'), 'w'), indent=1, sort_keys=True)
print('characters', len(chars), dict(cstat))
print('  not in XML2 stats (reachable):', sorted(c for c, d in chars.items() if not d['in_xml2_stats'] and d['reachable_zones'])[:80])
print('  not in XML1 stats:', sorted(c for c, d in chars.items() if not d['in_xml1_stats']))
print('actors: collisions', len(coll_actor), 'free prefix', free_prefix, 'xml2 skin range', agg['actors']['xml2_skin_range'])
print('sound banks: xml1', len(b1), 'xml2', len(b2), 'name collisions', sorted(set(b1) & set(b2)))
print('zone soundfiles:', {k: (v['zones'], v['in_xml1'], v['in_xml2']) for k, v in bank_need.items()})
print('music refs:', agg['sound_banks']['music_refs'])
print('sound prefixes:', agg['sound_banks']['sound_ref_prefixes'])
print('missing fns:', dict(miss_fn.most_common()), 'zones', zones_needing_fn)
print('sigchg:', dict(sig_fn))
print('not crlf scripts:', len(not_crlf), sorted(not_crlf)[:10])
print('ref status totals:', dict(status_tot))
for k, v in miss_ref.items():
    print('  missing', k, len(v), sorted(v)[:25])
print('bundle-listed but absent:', bundle_missing[:30], len(bundle_missing))
print('kept xml2 versions:', len(kept), list(kept.most_common(30)))
