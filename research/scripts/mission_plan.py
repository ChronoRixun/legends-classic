# SUPERSEDED (M3 phase 1b, tools/xml1build/SPEC.md 27.7): prepare stage P2 (tools/xml1build/prepare/tables.py,
# mission_plan() and the mission texts) regenerates this output from the user's disc image and XML2 install; builds never run this
# script. It stays as history and as the generator of the tracked research copy (the developer-mode input and
# P2's byte-for-byte equivalence reference). Change the stage, not this file.
"""Plan how XML1's per-mission objective files map onto XML2's act-based mission system.

XML2 hard limits (XMen2.exe):
  * max 25 mission files in data/missions/missions.xmlb           (0x48908a cmp [0x72b56c],0x19)
  * max 299 objectives across ALL mission files (state bytes)      (0x4885c0 cmp idx,0x12b; array 0x72b118)
  * max 75 objectives loaded for the current act                    (0x4899e0 cmp [edi+0x7d78],0x4b)
  * only missions whose act == current act are loaded               (0x489130; setCurrentAct(i))
XML1: one mission file per mission, loaded by beginMission(); objective names repeat across missions.

Plan: walk XML1 missions in campaign order (data/missions/missions.xml order, then any other mission
that is referenced by a script / inline script / zone world entity), pack consecutive missions into
XML2 'act' groups.  A mission joins the current group unless (a) the group would exceed 75
objectives or (b) it redefines an objective name already in the group with different text.
Every XML1 objective keeps its name (scripts need no objective renames).
beginMission(m) then becomes setCurrentAct(group(m)) + per-objective resets (see rewrite_scripts.py).

Output: mission_plan.json  {missions: {name: {...}}, groups: [...]}, and generated XML2 mission text
files under out/data/missions/*.xml (text form; compile with tools/xmlb.py encode).
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, collections, sys
import xml.etree.ElementTree as ET
HERE = os.path.dirname(os.path.abspath(__file__))
MDIR = _REPO + '/xml1_assets/data/missions'
OUT = os.path.join(HERE, 'out', 'data', 'missions')
os.makedirs(OUT, exist_ok=True)


def load_mission(name):
    for ext in ('.eng', '.xml'):
        p = os.path.join(MDIR, name + ext)
        if os.path.exists(p):
            t = open(p, encoding='latin-1').read()
            t = re.sub(r'&(?!(amp|lt|gt|quot|apos|#\d+);)', '&amp;', t)
            try:
                return ET.fromstring(t), p
            except ET.ParseError as e:
                return None, f'{p}: {e}'
    return None, None


order = [m.get('name') for m in ET.parse(os.path.join(MDIR, 'missions.xml')).getroot()]
order_l = [o.lower() for o in order]

# referenced missions (scripts + inline + zones)
refs = collections.Counter()
ref_re = re.compile(r"(beginMission|beginSideMission|beginMissionHack|mission)\s*\(\s*['\"]([^'\"]+)['\"]")
for root in (_REPO + '/xml1_loose', _REPO + '/xml1_assets'):
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.endswith(('.py', '.eng', '.xml')) and 'missions' not in dp.replace('\\', '/').split('/')[-1:]:
                try:
                    t = open(os.path.join(dp, f), encoding='latin-1').read()
                except Exception:
                    continue
                for m in ref_re.finditer(t):
                    refs[m.group(2).lower()] += 1
                for m in re.finditer(r'<entity name="world"[^>]*\bmission="([^"]+)"', t):
                    refs[m.group(1).lower()] += 1

all_files = sorted({os.path.splitext(f)[0].lower() for f in os.listdir(MDIR)} - {'missions'})
campaign = [m for m in order_l]
extra = [m for m in all_files if m not in campaign and m in refs]
unused = [m for m in all_files if m not in campaign and m not in refs]
seq = campaign + extra

missions = {}
for m in seq:
    root, p = load_mission(m)
    if root is None:
        missions[m] = {'file': p, 'objectives': [], 'error': p is not None}
        continue
    objs = []
    for o in root.iter('OBJECTIVE'):
        objs.append(dict(o.attrib))
    missions[m] = {'file': os.path.basename(p), 'attrs': dict(root.attrib), 'objectives': objs,
                   'required': [h.get('name') for h in root.iter('REQUIREDHERO')],
                   'restricted': [h.get('name') for h in root.iter('RESTRICTEDHERO')],
                   'recommended': [h.get('name') for h in root.iter('RECOMMENDEDHERO')],
                   'mustlive': [h.get('name') for h in root.iter('MUSTLIVEHERO')]}


def sig(o):
    return (o.get('descname', ''), o.get('description', ''), o.get('count', ''))


groups = []
cur = {'missions': [], 'objs': {}}
for m in seq:
    objs = missions[m]['objectives']
    names = {o['name'].lower(): o for o in objs}
    new = {n for n in names if n not in cur['objs']}
    conflict = [n for n in names if n in cur['objs'] and sig(cur['objs'][n]) != sig(names[n])]
    if cur['missions'] and (len(cur['objs']) + len(new) > 75 or conflict):
        groups.append(cur)
        cur = {'missions': [], 'objs': {}}
    cur['missions'].append(m)
    for n, o in names.items():
        cur['objs'].setdefault(n, o)
groups.append(cur)

total = sum(len(g['objs']) for g in groups)
plan = {'limits': {'files': 25, 'objectives_total': 299, 'objectives_per_act': 75},
        'n_groups': len(groups), 'n_objectives_total': total,
        'unused_mission_files': unused, 'groups': [], 'missions': {}}
for i, g in enumerate(groups, 1):
    gname = f'x1_act{i:02d}'
    plan['groups'].append({'file': gname, 'act': i, 'missions': g['missions'], 'n_objectives': len(g['objs'])})
    for m in g['missions']:
        plan['missions'][m] = {**missions[m], 'act': i, 'group_file': gname}
    # write XML2-shaped mission file (text).  XML2 attrs: name descname description enabled count xp
    # major parentname type zone.  XML1-only attrs (updatedescription, required) are dropped.
    root = ET.Element('MISSION', {'act': str(i)})
    for n, o in g['objs'].items():
        a = {'name': o['name'], 'descname': o.get('descname', o['name']),
             'enabled': 'false', 'major': 'true', 'type': 'normal'}
        if o.get('description'):
            a['description'] = o['description']
        if o.get('count'):
            a['count'] = o['count']
        a['xp'] = o.get('xp', '0')
        ET.SubElement(root, 'OBJECTIVE', dict(sorted(a.items())))
    ET.indent(root)
    open(os.path.join(OUT, gname + '.xml'), 'w', encoding='latin-1').write(ET.tostring(root, encoding='unicode'))
idx = ET.Element('MISSIONS')
for g in plan['groups']:
    ET.SubElement(idx, 'MISSION', {'name': g['file']})
ET.indent(idx)
open(os.path.join(OUT, 'missions.xml'), 'w').write(ET.tostring(idx, encoding='unicode'))
json.dump(plan, open(os.path.join(HERE, 'mission_plan.json'), 'w'), indent=1)
print(f'{len(seq)} XML1 missions in play ({len(campaign)} campaign + {len(extra)} referenced extras); '
      f'{len(unused)} unreferenced mission files ignored: {unused}')
print(f'{len(groups)} XML2 act groups, {total} objectives total (limit 299)')
for g in plan['groups']:
    print(f"  act {g['act']:2} {g['file']}: {g['n_objectives']:3} objectives  <- {', '.join(g['missions'])}")
