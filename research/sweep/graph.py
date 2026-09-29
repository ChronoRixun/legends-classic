"""Build the XML1 progression graph over zones, scripts, conversations, dialogs and missions, then
walk it from New Game.

New Game in XML1: main menu item usecmd="newgame" -> handler default.xbe 0x18d0b0 -> console command
"beginmission alison" (0x18d118; "beginmissionhack demo" when the demo flag [0x498db0] is set).

Edges:
  zone     -> script (bundle 'script' entries, zonescript, entity script attrs, precache script),
              conv (precache conversation / bundle xml conversations), dialog (precache dialog / xml_resident),
              zone (instanced zonelinkent nextzone), inline attr scripts' loads
  script   -> zone (loadZone/loadMap*), mission (beginMission*/mission), conv (startConversation),
              dialog (createPopupDialogXml*), inline popup options (addPopupDialogOption)
  conv     -> script (scriptFile / chosenScriptFile / conditionScriptFile)
  dialog   -> script (option script=)
  mission  -> script (scriptstart), zone (mapload)
Writes graph.json.
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, json, os, re, sys

sys.path.insert(0, _REPO + r'/research/sweep')
from sweeplib import parse_text_xml_robust, X1, X1A

SWEEP = _REPO + r'/research/sweep'
manifest = json.load(open(os.path.join(X1, '_fb_manifest.json')))
zones = json.load(open(os.path.join(SWEEP, 'zones.json')))
MP = 'packages/generated/maps/'
ALLZ = set(zones)
by_base = collections.defaultdict(list)
for z in zones:
    by_base[z.rsplit('/', 1)[-1].lower()].append(z)

STR = r'\s*\(\s*["\']([^"\']*)["\']'
R_ZONE = re.compile(r'(?<![\w.])(loadZone|loadMap|loadMapChooseTeam|loadMapKeepTeam|loadMapAddTeam)' + STR, re.I)
R_MISSION = re.compile(r'(?<![\w.])(beginMission|beginMissionHack|beginSideMission|mission)' + STR, re.I)
R_CONV = re.compile(r'(?<![\w.])(startConversation)' + STR, re.I)
R_DIALOG = re.compile(r'(?<![\w.])(createPopupDialogXml|createPopupDialogXmlFilter)' + STR, re.I)
R_MOVIE = re.compile(r'(?<![\w.])(startMovie|startMoviePreview)' + STR, re.I)


def find(rel):
    for root in (X1, X1A):
        p = os.path.join(root, rel.lower())
        if os.path.exists(p):
            return p


def resolve_zone(cur, name):
    n = name.strip().replace('\\', '/').lower().strip('/')
    if n in ALLZ:
        return n
    cands = by_base.get(n.rsplit('/', 1)[-1], [])
    if cur:
        cur_dir = cur.rsplit('/', 1)[0]
        same = [x for x in cands if x.rsplit('/', 1)[0] == cur_dir]
        if same:
            return same[0]
        area = [x for x in cands if x.split('/')[0] == cur.split('/')[0] and not x.startswith('demo/')]
        if len(area) == 1:
            return area[0]
    nondemo = [x for x in cands if not x.startswith(('demo/', 'arena/'))]
    if len(nondemo) == 1:
        return nondemo[0]
    if len(cands) == 1:
        return cands[0]
    return None


G = collections.defaultdict(set)
unresolved = []
movies_by_node = collections.defaultdict(set)


def script_node(v):
    v = v.strip().replace('\\', '/').lower()
    if v.startswith('scripts/'):
        v = v[8:]
    if v.endswith('.py'):
        v = v[:-3]
    return 'script:' + v


def add_text_edges(src, text, cur_zone):
    text = re.sub(r'(?<![\w.])game\.', '', text)
    for f, a in R_ZONE.findall(text):
        t = resolve_zone(cur_zone, a)
        if t:
            G[src].add('zone:' + t)
        else:
            unresolved.append((src, f, a))
    for f, a in R_MISSION.findall(text):
        G[src].add('mission:' + a.lower())
    for f, a in R_CONV.findall(text):
        G[src].add('conv:' + a.lower().replace('\\', '/'))
    for f, a in R_DIALOG.findall(text):
        a = a.lower().replace('\\', '/')
        G[src].add('dialog:' + (a[8:] if a.startswith('dialogs/') else a))
    for f, a in R_MOVIE.findall(text):
        movies_by_node[src].add(a)


# ---- zones
for z, r in zones.items():
    n = 'zone:' + z
    G[n]
    for name, kind in manifest[MP + z + '.fb']:
        if kind == 'script':
            G[n].add(script_node(name))
        elif name.startswith('conversations/') and name.endswith(('.eng', '.xml')):
            G[n].add('conv:' + name[14:].rsplit('.', 1)[0])
        elif name.startswith('dialogs/') and name.endswith(('.eng', '.xml')):
            G[n].add('dialog:' + name[8:].rsplit('.', 1)[0])
    w = r.get('world') or {}
    if w.get('zonescript') or find('scripts/' + z + '.py'):
        G[n].add(script_node(w.get('zonescript') or z))
    for k, v in (r.get('refs') or {}).items():
        if k in ('script', 'precache_script'):
            for s in v:
                G[n].add(script_node(s))
        if k == 'precache_conversation':
            for s in v:
                G[n].add('conv:' + s.lower())
        if k == 'precache_dialog':
            for s in v:
                G[n].add('dialog:' + s.lower())
    for l in r.get('links', []):
        if l['kind'] == 'zonelink' and l['instanced'] and l.get('target'):
            G[n].add('zone:' + l['target'])
        if l.get('source') == 'inline':
            if l['kind'] == 'mission':
                G[n].add('mission:' + l['raw'].lower())
            elif l.get('target'):
                G[n].add('zone:' + l['target'])

# ---- expand scripts / convs / dialogs / missions lazily
missions = json.load(open(os.path.join(SWEEP, 'graph.json')))['missions']
done = set()
queue = [n for n in list(G)]
for m in missions:
    queue.append('mission:' + m)
zone_of = {}  # remember a zone context for relative resolution
for z in zones:
    for t in G['zone:' + z]:
        zone_of.setdefault(t, z)
missing_nodes = set()
while queue:
    n = queue.pop()
    if n in done:
        continue
    done.add(n)
    typ, _, key = n.partition(':')
    cur = zone_of.get(n, '')
    if typ == 'script':
        p = find('scripts/' + key + '.py')
        if not p:
            missing_nodes.add(n)
        else:
            add_text_edges(n, open(p, encoding='latin-1').read(), cur)
    elif typ in ('conv', 'dialog'):
        base = ('conversations/' if typ == 'conv' else 'dialogs/') + key
        p = find(base + '.eng') or find(base + '.xml')
        if not p:
            missing_nodes.add(n)
        else:
            root = parse_text_xml_robust(p)
            for el in root.iter():
                for k, v in el.attrib.items():
                    if k in ('scriptfile', 'chosenscriptfile', 'conditionscriptfile', 'script') and v.strip():
                        if '(' in v:
                            add_text_edges(n, v, cur)
                        else:
                            G[n].add(script_node(v))
    elif typ == 'mission':
        m = missions.get(key)
        if not m:
            missing_nodes.add(n)
        else:
            if m.get('scriptstart'):
                G[n].add(script_node(m['scriptstart']))
            if m.get('mapload'):
                t = resolve_zone('', m['mapload'])
                if t:
                    G[n].add('zone:' + t)
                else:
                    unresolved.append((n, 'mapload', m['mapload']))
    for t in G[n]:
        zone_of.setdefault(t, cur)
        if t not in done:
            queue.append(t)

# ---- zone-level projection and reachability
def zone_succ(z):
    out, seen, st = set(), set(), list(G['zone:' + z])
    via = {}
    while st:
        n = st.pop()
        if n in seen:
            continue
        seen.add(n)
        if n.startswith('zone:'):
            if n[5:] != z:
                out.add(n[5:])
            continue
        st.extend(G[n])
    return out


zg = {z: sorted(zone_succ(z)) for z in zones}
start = 'mission:alison'
reach, order, st = set(), [], [start]
nodes_seen = set()
while st:
    n = st.pop(0)
    if n in nodes_seen:
        continue
    nodes_seen.add(n)
    if n.startswith('zone:'):
        order.append(n[5:])
    st.extend(sorted(G[n]))
reach = set(order)
mission_reach = sorted(n[8:] for n in nodes_seen if n.startswith('mission:'))
graph = json.load(open(os.path.join(SWEEP, 'graph.json')))
graph.update({
    'zone_edges': zg,
    'reachable_from_new_game': order,
    'reachable_missions': mission_reach,
    'unreachable_by_category': {c: sorted(z for z, r in zones.items() if r['category'] == c and z not in reach)
                                for c in sorted({r['category'] for r in zones.values()})},
    'unresolved_zone_refs': sorted(set(map(tuple, unresolved))),
    'missing_nodes': sorted(missing_nodes),
    'movies_played': {n: sorted(v) for n, v in movies_by_node.items()},
    'movies_reachable': sorted({mv for n in nodes_seen for mv in movies_by_node.get(n, ())}),
})
for k in ('edges', 'reachable_from_start', 'unreachable_campaign'):
    graph.pop(k, None)
json.dump(graph, open(os.path.join(SWEEP, 'graph.json'), 'w'), indent=1, sort_keys=True)
print('nodes', len(G), 'reachable zones', len(order), 'reachable missions', len(mission_reach))
print('unreachable:', {k: len(v) for k, v in graph['unreachable_by_category'].items()})
print('unreachable campaign:', graph['unreachable_by_category'].get('campaign'))
print('unresolved:', graph['unresolved_zone_refs'][:40])
print('missing nodes:', len(missing_nodes), sorted(missing_nodes)[:60])
print('movies reachable:', graph['movies_reachable'])
