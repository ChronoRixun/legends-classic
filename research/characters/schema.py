"""Exhaustive schema diff of character stats (herostat+npcstat) and powerstyles/fightstyles, XML1 vs XML2.

For stats: every attribute name (lowercased) on <stats>, every child tag and its attributes, with counts in
each game and whether XML2's stats attribute parser (XMen2.exe FUN_004b9c40 @0x4b9c40) handles it.
Writes schema_stats.json and prints a table."""
import collections, glob, json, os, re
from common import *

# attribute names compared with _stricmp/strstr in XMen2.exe FUN_004b9c40 (see ghidra/decomp3.c)
X2_PARSER = set('''name charactername leadername leaderpowerup sounddir skirmish_boost skin effect_skin_ skin_
leaderskin mutantskin mutatechance characteranims footstepfx deathnode grabbolt powerstyle power1 power2 power3
power4 moveset1 level experience xpaward strength speed body mind weapon material counter heaviness npchealthscale
specific_health specific_attack specific_defense size team large selectable scale_factor resurrect aiclasstype
alertradius attackrange meleetimeroffset meleetimerrandomadd rangedtimeroffset grabchance pickupthrowchance
scriptlevel willflee teleportpathfail canfly canseestealthed fleedistance dangerrating ailevel aipower xpexempt
canthrowally aiforceranged ainocover combolevel ainomelee ainostraffe aimaxcoverheight canbeallythrown
ignoreboundsscaling inherit playable textureicon nonhumanoidskeleton scaleattacks targetheight autospend'''.split())
# attributes read directly by the stats loader FUN_0044c030 (binary-search lookups)
X2_LOADER = {'platform', 'name', 'charactername', 'skin', 'characteranims', 'team', 'level', 'playable', 'textureicon'}
COSTUMES_X2 = {'astonishing', 'aoa', '60s', '70s', 'weaponx', 'future', 'winter', 'civilian'}  # table @0x6d8aa0


def handled(attr):
    a = attr.lower()
    if a in X2_PARSER or a in X2_LOADER:
        return 'yes'
    if a.startswith('skin_'):
        return 'yes(costume ok)' if a[5:] in COSTUMES_X2 else 'NO(costume name not in XML2 table)'
    if a.startswith('effect_skin_'):
        return 'yes(costume ok)' if a[12:] in COSTUMES_X2 else 'NO(costume name not in XML2 table)'
    return 'NO'


def collect(roots):
    s = collections.Counter()
    ch = collections.Counter()
    cha = collections.Counter()
    examples = {}
    for game_file, root in roots:
        for st in root.iter('stats'):
            for k, v in st.attrib.items():
                s[k.lower()] += 1
                examples.setdefault(('stats', k.lower()), (st.get('name'), v))
            for c in st.iter():
                if c is st:
                    continue
                ch[c.tag.lower()] += 1
                for k, v in c.attrib.items():
                    cha[(c.tag.lower(), k.lower())] += 1
                    examples.setdefault((c.tag.lower(), k.lower()), (st.get('name'), v))
    return s, ch, cha, examples


x2roots = [(f, load_xmlb(f'{X2}/Data/{f}.engb')) for f in ('herostat', 'npcstat')]
x1roots = [(f, parse_x1_text(f'{X1L}/data/{f}.eng')) for f in ('herostat', 'npcstat')]
s2, c2, ca2, ex2 = collect(x2roots)
s1, c1, ca1, ex1 = collect(x1roots)
out = {'stats_attrs': [], 'child_tags': [], 'child_attrs': []}
print('== <stats> attributes (count in XML1 / XML2, XML2 parser handles?)')
for a in sorted(set(s1) | set(s2)):
    row = {'attr': a, 'x1': s1.get(a, 0), 'x2': s2.get(a, 0), 'x2_handles': handled(a),
           'x1_example': ex1.get(('stats', a)), 'x2_example': ex2.get(('stats', a))}
    out['stats_attrs'].append(row)
    flag = '' if row['x1'] == 0 or row['x2'] else '  <-- XML1-only'
    print(f"  {a:24} x1={row['x1']:4} x2={row['x2']:4} handled={row['x2_handles']:10} {flag}"
          f"{'  e.g. ' + str(row['x1_example']) if flag else ''}")
print('\n== child elements under <stats> (all depths)')
for t in sorted(set(c1) | set(c2)):
    out['child_tags'].append({'tag': t, 'x1': c1.get(t, 0), 'x2': c2.get(t, 0)})
    print(f'  {t:20} x1={c1.get(t, 0):5} x2={c2.get(t, 0):5}{"  <-- XML1-only" if not c2.get(t) else ""}')
print('\n== child element attributes')
for t, a in sorted(set(ca1) | set(ca2)):
    row = {'tag': t, 'attr': a, 'x1': ca1.get((t, a), 0), 'x2': ca2.get((t, a), 0),
           'x1_example': ex1.get((t, a)), 'x2_example': ex2.get((t, a))}
    out['child_attrs'].append(row)
    flag = '  <-- XML1-only' if row['x1'] and not row['x2'] else ('  (XML2-only)' if not row['x1'] else '')
    print(f'  {t + "." + a:34} x1={row["x1"]:5} x2={row["x2"]:5}{flag}{"  e.g. " + str(row["x1_example"]) if flag == "  <-- XML1-only" else ""}')


# powerstyles / fightstyles: tag+attr presence over all files
def style_schema(files, loader):
    tags, attrs = collections.Counter(), collections.Counter()
    for f in files:
        try:
            r = loader(f)
        except Exception as e:
            print('  parse fail', f, e)
            continue
        for el in r.iter():
            tags[el.tag.lower()] += 1
            for k in el.attrib:
                attrs[(el.tag.lower(), k.lower())] += 1
    return tags, attrs


for kind in ('powerstyles', 'fightstyles'):
    f1 = [p for p in glob.glob(f'{X1L}/data/{kind}/*') if p.endswith(('.xml', '.eng'))]
    f2 = glob.glob(f'{X2}/Data/{kind}/*.XMLB') + glob.glob(f'{X2}/Data/{kind}/*.xmlb')
    t1, a1 = style_schema(f1, parse_x1_text)
    t2, a2 = style_schema(sorted(set(f2)), load_xmlb)
    print(f'\n== {kind}: XML1 {len(f1)} files, XML2 {len(set(f2))} files')
    print('  XML1-only tags:', sorted(t for t in t1 if t not in t2))
    print('  XML2-only tags:', sorted(t for t in t2 if t not in t1))
    x1o = sorted(f'{t}.{a}({n})' for (t, a), n in a1.items() if (t, a) not in a2)
    print(f'  XML1-only tag.attr ({len(x1o)}):', x1o)
    out[kind] = {'x1_only_tags': sorted(t for t in t1 if t not in t2), 'x2_only_tags': sorted(t for t in t2 if t not in t1),
                 'x1_only_attrs': x1o}

# values table: every XML1 symbolic value must exist in XML2 with the same numbers
v1 = {e.get('name'): dict(e.attrib) for e in parse_x1_text(f'{X1L}/data/values.xml').iter('value')}
v2 = {e.get('name'): dict(e.attrib) for e in load_xmlb(f'{X2}/Data/values.XMLB').iter('value')}
missing = [n for n in v1 if n not in v2]
diff = [n for n in v1 if n in v2 and {k.lower(): v for k, v in v1[n].items()} != v2[n]]
print(f'\n== values: XML1 {len(v1)} entries, missing in XML2: {missing}, different: {diff[:20]}')
out['values'] = {'x1': len(v1), 'missing_in_x2': missing, 'different': diff}
json.dump(out, open(os.path.join(HERE, 'schema_stats.json'), 'w'), indent=1, default=str)
