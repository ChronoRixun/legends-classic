"""Zone-precise scope analysis of XML1 mission vars / mission flags / game vars.

Uses xml1_loose/_fb_manifest.json: every zone bundle packages/generated/maps/<zone>.fb lists the
scripts (kind 'script'), conversations and the zone .eng it carries.  For each variable we compute the
set of zones that SET it and the zones that READ it.  Sources: .py scripts, inline scripts inside
conversation .eng files and zone .eng files (actscript=..., etc.), and mission start scripts
(xml1_assets/scripts/missions/*.py, zone = 'MISSIONSTART').

A variable read in a zone where it is never set (but set elsewhere) needs a store that survives zone
loads -> XML2 GAME scope.  Variables only ever set+read inside one zone can use XML2 ZONE scope.

Output: var_zones.json {name: {...}} and var_zones.txt
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, collections, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bescript import parse_file

LOOSE = _REPO + '/xml1_loose'
ASSETS = _REPO + '/xml1_assets'
man = json.load(open(f'{LOOSE}/_fb_manifest.json'))

STORE = {'setMissionVar': ('mvar', 'set'), 'getMissionVar': ('mvar', 'get'),
         'setMissionFlag': ('mflag', 'set'), 'getMissionFlag': ('mflag', 'get'),
         'setGameVar': ('gvar', 'set'), 'getGameVar': ('gvar', 'get')}

file_zones = collections.defaultdict(set)   # 'scripts/x/y.py' or 'conversations/..eng' or 'maps/..eng' -> zones
zone_mission = {}
for b, files in man.items():
    if not b.startswith('packages/generated/maps/'):
        continue
    zone = b[len('packages/generated/maps/'):-3]
    for f, k in files:
        f = f.lower()
        if f.endswith(('.py', '.eng')):
            file_zones[f].add(zone)
for dp, dn, fn in os.walk(f'{LOOSE}/maps'):
    for f in fn:
        if f.endswith('.eng'):
            p = os.path.join(dp, f).replace('\\', '/')
            t = open(p, encoding='latin-1').read(4000)
            m = re.search(r'<entity name="world"[^>]*\bmission="([^"]*)"', t)
            zone_mission[p[len(LOOSE) + 6:-4]] = m.group(1) if m else ''

acc = collections.defaultdict(lambda: {'kind': set(), 'set': collections.defaultdict(list),
                                        'get': collections.defaultdict(list)})


def record(fn, name, where, zones):
    kind, op = STORE[fn]
    e = acc[name]
    e['kind'].add(kind)
    for z in zones or ['<no zone>']:
        e[op][z].append(where)


# 1) .py scripts
nscripts = 0
for root, tag in ((f'{LOOSE}/scripts', 'loose'), (f'{ASSETS}/scripts', 'assets')):
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if not f.lower().endswith('.py'):
                continue
            p = os.path.join(dp, f).replace('\\', '/')
            rel = 'scripts/' + p[len(root) + 1:].lower()
            zones = sorted(file_zones.get(rel, []))
            if rel.startswith('scripts/missions/'):
                zones = ['MISSIONSTART']
            elif rel.startswith('scripts/menus/'):
                zones = ['MENU']
            nscripts += 1
            for ln, call, ctx in parse_file(p).calls():
                if call.name in STORE and call.args:
                    a = call.args[0]
                    name = a.value if a.kind == 'str' else f'<{a.text}>'
                    record(call.name, name, f'{rel}:{ln.no}', zones)

# 2) inline scripts in conversations + zone files (.eng only; .fre/.ger duplicate them)
inl = re.compile(r"\b(setMissionVar|getMissionVar|setMissionFlag|getMissionFlag|setGameVar|getGameVar)\s*\(\s*['\"]([^'\"]*)['\"]")
ninline = collections.Counter()
for sub in ('conversations', 'maps', 'dialogs'):
    for dp, dn, fn in os.walk(f'{LOOSE}/{sub}'):
        for f in fn:
            if not f.endswith('.eng'):
                continue
            p = os.path.join(dp, f).replace('\\', '/')
            rel = p[len(LOOSE) + 1:].lower()
            zones = sorted(file_zones.get(rel, []))
            if sub == 'maps':
                zones = [rel[5:-4]]
            t = open(p, encoding='latin-1').read()
            for m in inl.finditer(t):
                ninline[sub] += 1
                record(m.group(1), m.group(2), rel + ' (inline)', zones)

res = {}
for name, e in acc.items():
    sz, gz = set(e['set']), set(e['get'])
    foreign_reads = sorted(gz - sz)          # zones that read but never set it
    res[name] = {'kind': sorted(e['kind']), 'set_zones': sorted(sz), 'get_zones': sorted(gz),
                 'read_without_local_set': foreign_reads,
                 'needs_game_scope': bool(foreign_reads) and bool(sz),
                 'never_set': not sz, 'never_read': not gz,
                 'missions': sorted({zone_mission.get(z, '?') for z in sz | gz}),
                 'n_set': sum(len(v) for v in e['set'].values()), 'n_get': sum(len(v) for v in e['get'].values()),
                 'sites': {'set': {z: v for z, v in e['set'].items()}, 'get': {z: v for z, v in e['get'].items()}}}
json.dump(res, open(os.path.join(HERE, 'var_zones.json'), 'w'), indent=1)

out = [f'scripts parsed: {nscripts}; inline store calls found in data: {dict(ninline)}',
       f'distinct names: {len(res)}']
by = collections.Counter()
for n, r in res.items():
    by[('+'.join(r['kind']), 'GAME' if r['needs_game_scope'] else ('never-set' if r['never_set'] else 'ZONE-ok'))] += 1
out.append('classification (store kind, scope needed): ' + ', '.join(f'{k}: {v}' for k, v in sorted(by.items())))
out.append('')
for n in sorted(res, key=lambda k: (not res[k]['needs_game_scope'], '+'.join(res[k]['kind']), k.lower())):
    r = res[n]
    tag = 'GAME' if r['needs_game_scope'] else ('NEVERSET' if r['never_set'] else 'zone')
    out.append(f'{tag:8} {"+".join(r["kind"]):10} {n:14} set@{",".join(r["set_zones"])[:70]}  read-elsewhere@{",".join(r["read_without_local_set"])[:70]}')
open(os.path.join(HERE, 'var_zones.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out[:4]))
