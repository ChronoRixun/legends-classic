"""Whole-game conversion sweep.

1. Converts EVERY XML1 map bundle (packages/generated/maps/**.fb except maps/package/*) into the writable
   XML2 copy at research/sweep/xml2_copy with tools/convert_zone.py's Converter, continuing on errors.
   Text-XML that the stock parse_text_xml rejects is recorded, then parsed with the robust normaliser
   (sweeplib.normalise_text_xml) so the rest of the zone still converts.
2. Analyses each zone's XML1 source: world entity, characters (.chr + spawners), sound banks / sound refs,
   script functions (bundle scripts + zone script + inline attribute scripts), referenced files and whether
   they resolve, zone links (nextzone / prevzone / loadZone/loadMap calls).
3. Resolves short zone names to full paths and builds the XML1 zone graph from the New Game entry point.
Writes zones.json and graph.json; prints a summary.
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, json, os, re, sys, time, traceback

sys.path.insert(0, _REPO + r'/tools')
sys.path.insert(0, _REPO + r'/research/sweep')
import convert_zone, xmlb
from sweeplib import parse_text_xml_robust, walk_files, load_xmlb, X1, X1A, X2
from script_calls import calls_in

SWEEP = _REPO + r'/research/sweep'
COPY = os.path.join(SWEEP, 'xml2_copy')
SF = json.load(open(os.path.join(SWEEP, 'script_functions.json')))
T1 = {k.lower(): v for k, v in SF['xml1'].items()}
T2 = {k.lower(): v for k, v in SF['xml2'].items()}

# ---------------------------------------------------------------- parser hook
_orig_parse = convert_zone.parse_text_xml
PARSE_FAILS = {}


def hooked_parse(path):
    try:
        return _orig_parse(path)
    except Exception as e:
        PARSE_FAILS[os.path.relpath(path, X1).replace(os.sep, '/')] = str(e)
        return parse_text_xml_robust(path)


convert_zone.parse_text_xml = hooked_parse


class SweepConverter(convert_zone.Converter):
    pass


# ---------------------------------------------------------------- helpers
MAPS_PREFIX = 'packages/generated/maps/'


def classify(z):
    parts = z.split('/')
    if parts[0] == 'package':
        return 'package'
    if parts[0] == 'mocap':
        return 'briefing_mocap'
    if parts[0] == 'cinematics':
        return 'cinematic'
    if parts[0] == 'arena':
        return 'arena'
    if parts[0] == 'demo':
        return 'demo_copy'
    if parts[0] == 'menu':
        return 'menu_background'
    return 'campaign'


FILE_ATTRS = {
    'model': ('models/{}', ['.igb']),
    'deatheffect': ('effects/{}', ['.xml']), 'xdeatheffect': ('effects/{}', ['.xml']),
    'loopfx': ('effects/{}', ['.xml']), 'acteffect': ('effects/{}', ['.xml']),
    'ambienteffect': ('effects/{}', ['.xml']), 'splasheffect': ('effects/{}', ['.xml']),
    'wakeeffect': ('effects/{}', ['.xml']), 'trailfx': ('effects/{}', ['.xml']),
    'motionpath': ('motionpaths/{}', ['.igb']),
    'skybox': ('skybox/{}', ['.igb']),
}
SCRIPT_ATTRS = {'actscript', 'monster_spawnscript', 'monster_deathscript', 'deathscript', 'monster_actscript',
                'spawnscript', 'zonescript', 'monster_painscript', 'firstspawnscript', 'painscript',
                'deactscript', 'monster_actscript', 'script'}
SOUND_ATTRS = {'deathsound', 'actsound', 'spawnsoundloop', 'actsoundloop', 'spawnsound', 'monster_spawnsound',
               'rotatesound', 'monster_spawnsoundloop', 'soundloop', 'sound'}
MUSIC_ATTRS = {'combatmusic', 'ambientmusic', 'intromusic'}
PRECACHE = {'conversation': ('conversations/{}', ['.eng']), 'dialog': ('dialogs/{}', ['.eng', '.xml']),
            'fx': ('effects/{}', ['.xml']), 'script': ('scripts/{}', ['.py']),
            'model': ('models/{}', ['.igb']), 'texture': ('textures/{}', ['.igb'])}
XML2_EXT = {'.xml': ['.xmlb'], '.eng': ['.xmlb', '.engb'], '.chr': ['.chrb'], '.nav': ['.navb'],
            '.igb': ['.igb'], '.py': ['.py']}


class Resolver:
    def __init__(self):
        self.x2 = walk_files(X2)
        self.x1 = walk_files(X1)
        self.x1a = walk_files(X1A)
        self.copy = None  # filled after conversion

    def status(self, rel_noext, exts):
        """rel_noext lowercase, forward slashes. Returns xml2 | converted | xml1_only | missing."""
        rel_noext = rel_noext.lower().replace('\\', '/').strip('/')
        for e in exts:
            for e2 in XML2_EXT.get(e, [e]):
                if rel_noext + e2 in self.x2:
                    return 'xml2'
        for e in exts:
            for e2 in XML2_EXT.get(e, [e]):
                if self.copy and rel_noext + e2 in self.copy:
                    return 'converted'
        for e in exts:
            if rel_noext + e in self.x1 or rel_noext + e in self.x1a:
                return 'xml1_only'
        return 'missing'


def is_inline_script(v):
    return '(' in v or '=' in v


def zone_bundle_scripts(manifest, zone):
    return [n for n, k in manifest[MAPS_PREFIX + zone + '.fb'] if k == 'script']


LOAD_FUNCS = {'loadzone', 'loadmap', 'loadmapchooseteam', 'loadmapkeepteam', 'loadmapaddteam', 'restartzone',
              'beginmission', 'beginmissionhack', 'beginsidemission', 'mission'}
LOAD_RE = re.compile(r'(?<![\w.])(loadZone|loadMap|loadMapChooseTeam|loadMapKeepTeam|loadMapAddTeam|beginMission|'
                     r'beginMissionHack|beginSideMission|mission)\s*\(\s*["\']([^"\']*)["\']', re.I)
MOVIE_RE = re.compile(r'(?<![\w.])(startMovie|startMoviePreview|setNextMovie)\s*\(\s*["\']([^"\']*)["\']', re.I)


def script_text(rel):
    for root in (X1, X1A):
        p = os.path.join(root, rel)
        if os.path.exists(p):
            return open(p, encoding='latin-1').read()
    return None


def analyse_calls(texts):
    calls = collections.Counter()
    for t in texts:
        calls.update(calls_in(t))
    missing = {k: n for k, n in calls.items() if k.lower() in T1 and k.lower() not in T2}
    sigchg = {k: [T1[k.lower()]['args'], T2[k.lower()]['args']] for k in calls
              if k.lower() in T1 and k.lower() in T2 and T1[k.lower()]['args'] != T2[k.lower()]['args']}
    unknown = {k: n for k, n in calls.items() if k.lower() not in T1 and k.lower() not in T2}
    return calls, missing, sigchg, unknown


def main():
    t0 = time.time()
    manifest = json.load(open(os.path.join(X1, '_fb_manifest.json')))
    bundles = sorted(b for b in manifest if b.startswith(MAPS_PREFIX))
    zones = [b[len(MAPS_PREFIX):-3] for b in bundles]
    conv_zones = [z for z in zones if classify(z) != 'package']
    c = SweepConverter(X1, COPY)
    res = Resolver()
    rec = {}
    for z in conv_zones:
        r = rec[z] = {'category': classify(z), 'bundle_entries': len(manifest[MAPS_PREFIX + z + '.fb'])}
        w0, k0, m0 = len(c.written), len(c.kept_xml2), len(c.missing)
        f0 = set(PARSE_FAILS)
        try:
            c.zone(z)
            r['convert'] = 'ok'
        except Exception as e:
            r['convert'] = 'error'
            r['error'] = '%s: %s' % (type(e).__name__, e)
            r['traceback'] = traceback.format_exc().splitlines()[-4:]
        r['written'] = len(c.written) - w0
        r['kept_xml2'] = sorted(set(c.kept_xml2[k0:]))
        r['missing_bundle_files'] = sorted(set(c.missing[m0:]))
        r['parse_fallbacks'] = sorted(set(PARSE_FAILS) - f0)
    print('converted %d zones in %.0fs' % (len(conv_zones), time.time() - t0))

    res.copy = walk_files(COPY)
    all_zones = set(conv_zones)
    by_base = collections.defaultdict(list)
    for z in conv_zones:
        by_base[z.rsplit('/', 1)[-1].lower()].append(z)

    def resolve_zone(cur, name):
        n = name.strip().replace('\\', '/').lower()
        if not n:
            return None, 'empty'
        if n in all_zones:
            return n, 'full'
        cands = by_base.get(n.rsplit('/', 1)[-1], [])
        cur_dir = cur.rsplit('/', 1)[0]
        same = [x for x in cands if x.rsplit('/', 1)[0] == cur_dir]
        if same:
            return same[0], 'same_dir'
        # prefer non-demo candidates in the same top-level area
        area = [x for x in cands if x.split('/')[0] == cur.split('/')[0]]
        if len(area) == 1:
            return area[0], 'same_area'
        nondemo = [x for x in cands if classify(x) == 'campaign']
        if len(nondemo) == 1:
            return nondemo[0], 'unique_campaign'
        if len(cands) == 1:
            return cands[0], 'unique'
        return None, 'ambiguous:' + ','.join(cands) if cands else 'unresolved'

    # missions: data/missions/<m>.eng scriptstart -> scripts/<scriptstart>.py -> loadMap targets
    missions = {}
    mdir = os.path.join(X1A, 'data', 'missions')
    for f in sorted(os.listdir(mdir)):
        if not f.endswith(('.eng', '.xml')):
            continue
        name = f.rsplit('.', 1)[0]
        try:
            root = parse_text_xml_robust(os.path.join(mdir, f))
        except Exception as e:
            missions[name] = {'error': str(e)}
            continue
        m = missions.setdefault(name, {})
        m['file'] = 'data/missions/' + f
        m['root'] = root.tag
        m.update(root.attrib)
        m['objectives'] = len(root.findall('.//OBJECTIVE'))
        m['requiredheroes'] = [e.get('name') for e in root.iter('REQUIREDHERO')]
        ss = root.get('scriptstart')
        if ss:
            txt = script_text('scripts/' + ss + '.py')
            m['script_found'] = txt is not None
            if txt:
                m['loads'] = [[f_, a] for f_, a in LOAD_RE.findall(txt)]
                m['movies'] = [a for _, a in MOVIE_RE.findall(txt)]

    all_calls = collections.Counter()
    for z in conv_zones:
        r = rec[z]
        zx = None
        for n_, k_ in manifest[MAPS_PREFIX + z + '.fb']:
            if k_ == 'zonexml' and n_.endswith(('.eng', '.xml')) and os.path.exists(os.path.join(X1, n_)):
                zx = os.path.join(X1, n_)
                r['zone_xml'] = n_
                break
        if zx is None:
            r['zone_xml'] = 'missing'
            r['links'] = []
            continue
        root = parse_text_xml_robust(zx)
        ents = {e.get('name'): e for e in root.iter('entity')}
        instanced = collections.Counter(e.get('type') for e in root.iter('entinst'))
        world = ents.get('world')
        r['world'] = dict(world.attrib) if world is not None else None
        r['entity_templates'] = len(ents)
        r['instances'] = sum(instanced.values())
        r['classes'] = dict(collections.Counter(e.get('classname', '') for e in ents.values()
                                                if instanced.get(e.get('name'))))
        # characters
        chr_path = os.path.join(X1, 'maps', z + '.chr')
        chars = []
        if os.path.exists(chr_path):
            chars = [e.get('name') for e in parse_text_xml_robust(chr_path).iter('character')]
        r['chr_characters'] = chars
        r['spawner_characters'] = sorted({e.get('character') for e in ents.values()
                                          if e.get('character') and instanced.get(e.get('name'))})
        # sounds
        snd = collections.Counter()
        music = set()
        for e in root.iter():
            for k, v in e.attrib.items():
                if k in SOUND_ATTRS and v.strip():
                    snd[v.strip().replace('\\', '/').lower()] += 1
                if k in MUSIC_ATTRS and v.strip():
                    music.add(v.strip())
        for p in root.iter('precache'):
            if p.get('type') == 'sound':
                snd[p.get('filename', '').replace('\\', '/').lower()] += 1
        # file references
        refs = collections.defaultdict(dict)
        for e in root.iter():
            for k, v in e.attrib.items():
                v = v.strip()
                if not v:
                    continue
                if k == 'motionpath':
                    # value is <motionpath file>/<path name inside it>
                    refs[k][v] = res.status('motionpaths/' + v.replace(chr(92), '/').rsplit('/', 1)[0], ['.igb'])
                elif k in FILE_ATTRS:
                    pat, exts = FILE_ATTRS[k]
                    refs[k][v] = res.status(pat.format(v), exts)
                elif k in SCRIPT_ATTRS and not is_inline_script(v):
                    refs['script'][v] = res.status('scripts/' + v, ['.py'])
                elif k == 'automap_texture':
                    v2 = v if v.lower().startswith('textures/') else 'textures/automap/' + v
                    refs['automap'][v] = res.status(v2, ['.igb'])
                elif k == 'texture' and e.tag == 'entity':
                    base = os.path.splitext(v)[0]
                    refs['texture'][v] = res.status(base, ['.igb', '.png'])
                elif k == 'tilemodelfolder':
                    pre = 'models/' + v.lower().strip('/') + '/'
                    ok2 = any(x.startswith(pre) for x in res.x2)
                    ok1 = any(x.startswith(pre) for x in res.x1)
                    refs['tilemodelfolder'][v] = 'xml2' if ok2 else ('xml1_only' if ok1 else 'missing')
        for p in root.iter('precache'):
            t = p.get('type')
            fn = p.get('filename', '')
            if t in PRECACHE and fn:
                pat, exts = PRECACHE[t]
                st = res.status(pat.format(fn), exts)
                if st == 'missing':  # model/texture precaches sometimes carry a full path (hud/hud_head_0101)
                    st = res.status(fn, exts)
                refs['precache_' + t][fn] = st
            elif t and t != 'sound':
                refs['precache_other'][t + ':' + fn] = 'unchecked'
        r['refs'] = {k: dict(sorted(v.items())) for k, v in refs.items()}
        r['refs_missing'] = {k: sorted(n for n, s in v.items() if s == 'missing') for k, v in refs.items()
                             if any(s == 'missing' for s in v.values())}
        r['refs_status_counts'] = dict(collections.Counter(s for v in refs.values() for s in v.values()))
        # scripts
        texts = []
        script_files = set(zone_bundle_scripts(manifest, z))
        zs = world.get('zonescript') if world is not None else None
        if zs or script_text('scripts/' + z + '.py') is not None:
            script_files.add('scripts/' + (zs or z) + '.py')
        for k in ('script',):
            for v in refs.get(k, {}):
                script_files.add('scripts/' + v + '.py')
        missing_scripts = []
        loads = []
        movies = []
        crlf_bad = []
        for sf in sorted(script_files):
            t = script_text(sf.lower())
            if t is None:
                missing_scripts.append(sf)
                continue
            t = re.sub(r'(?<![\w.])game\.', '', t)
            texts.append(t)
            raw = open(os.path.join(X1, sf.lower()) if os.path.exists(os.path.join(X1, sf.lower()))
                       else os.path.join(X1A, sf.lower()), 'rb').read()
            if b'\n' in raw.replace(b'\r\n', b''):
                crlf_bad.append(sf)
            loads += [[f_, a, sf] for f_, a in LOAD_RE.findall(t)]
            movies += [a for _, a in MOVIE_RE.findall(t)]
        inline = []
        for e in root.iter():
            for k, v in e.attrib.items():
                if k in SCRIPT_ATTRS and is_inline_script(v):
                    inline.append(v.replace('\\n', '\n').replace('\\r', '\n'))
        texts += inline
        for t in inline:
            loads += [[f_, a, 'inline'] for f_, a in LOAD_RE.findall(t)]
        calls, missing, sigchg, unknown = analyse_calls(texts)
        all_calls.update(calls)
        r['scripts'] = {'files': len(script_files), 'missing_files': missing_scripts, 'inline': len(inline),
                        'not_crlf': crlf_bad, 'distinct_calls': len(calls),
                        'missing_in_xml2': missing, 'signature_changed': sigchg, 'unknown_calls': unknown}
        r['movies'] = sorted(set(movies))
        r['sounds'] = {'soundfile': world.get('soundfile') if world is not None else None,
                       'music': sorted(music), 'refs': len(snd),
                       'ref_prefixes': dict(collections.Counter(s.split('/')[0] for s in snd)),
                       'sample': sorted(snd)[:40]}
        # links
        links = []
        for e in ents.values():
            if e.get('classname') == 'zonelinkent' and e.get('nextzone'):
                tgt, how = resolve_zone(z, e.get('nextzone'))
                links.append({'kind': 'zonelink', 'raw': e.get('nextzone'), 'target': tgt, 'how': how,
                              'instanced': bool(instanced.get(e.get('name'))), 'entity': e.get('name'),
                              'description': e.get('description')})
        for e in ents.values():
            if e.get('classname') == 'playerstartent' and e.get('prevzone'):
                tgt, how = resolve_zone(z, e.get('prevzone'))
                links.append({'kind': 'prevzone', 'raw': e.get('prevzone'), 'target': tgt, 'how': how,
                              'instanced': bool(instanced.get(e.get('name'))), 'entity': e.get('name')})
        for f_, a, src in loads:
            if f_.lower() in ('beginmission', 'beginmissionhack', 'beginsidemission', 'mission'):
                links.append({'kind': 'mission', 'raw': a, 'func': f_, 'source': src})
            else:
                tgt, how = resolve_zone(z, a)
                links.append({'kind': 'script_load', 'raw': a, 'func': f_, 'target': tgt, 'how': how, 'source': src})
        r['links'] = links

    # graph from New Game: XML1 newgame handler (xbe 0x18d0b0) runs "beginmission alison"
    edges = collections.defaultdict(set)
    for z, r in rec.items():
        for l in r.get('links', []):
            if l['kind'] in ('zonelink', 'script_load') and l.get('target') and (l['kind'] != 'zonelink' or l['instanced']):
                edges[z].add(l['target'])
            if l['kind'] == 'mission':
                m = missions.get(l['raw'].lower())
                for f_, a in (m or {}).get('loads', []):
                    tgt, how = resolve_zone(z, a)
                    if tgt:
                        edges[z].add(tgt)
    start = None
    for f_, a in missions.get('alison', {}).get('loads', []):
        start = resolve_zone('', a)[0]
    seen, order = set(), []
    stack = [start] if start else []
    while stack:
        n = stack.pop(0)
        if n in seen:
            continue
        seen.add(n)
        order.append(n)
        stack.extend(sorted(edges.get(n, ())))
    # mission start zones
    mission_starts = {}
    for name, m in missions.items():
        for f_, a in m.get('loads', []):
            tgt, how = resolve_zone('', a)
            mission_starts.setdefault(name, []).append(tgt or ('?' + a))
    graph = {
        'new_game': {'xbe_newgame_handler': '0x18d0b0', 'command': 'beginmission alison',
                     'mission_script': missions.get('alison', {}).get('scriptstart'),
                     'mission_movies': missions.get('alison', {}).get('movies'), 'start_zone': start},
        'edges': {k: sorted(v) for k, v in sorted(edges.items())},
        'reachable_from_start': order,
        'unreachable_campaign': sorted(z for z in conv_zones if classify(z) == 'campaign' and z not in seen),
        'mission_start_zones': mission_starts,
        'missions': missions,
    }
    json.dump(rec, open(os.path.join(SWEEP, 'zones.json'), 'w'), indent=1, sort_keys=True)
    json.dump(graph, open(os.path.join(SWEEP, 'graph.json'), 'w'), indent=1, sort_keys=True)
    json.dump({'parse_fallbacks': PARSE_FAILS, 'all_calls': dict(all_calls)},
              open(os.path.join(SWEEP, 'sweep_misc.json'), 'w'), indent=1, sort_keys=True)
    # summary
    cats = collections.Counter(r['category'] for r in rec.values())
    print('zones by category', dict(cats))
    print('convert errors:', [(z, r['error']) for z, r in rec.items() if r['convert'] != 'ok'])
    print('parse fallbacks:', PARSE_FAILS)
    print('start zone', start, 'reachable', len(order), 'unreachable campaign', len(graph['unreachable_campaign']))
    print('done in %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
