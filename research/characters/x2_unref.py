# SUPERSEDED (M3 phase 1b, tools/xml1build/SPEC.md 27.7): prepare stage P2 (tools/xml1build/prepare/tables.py,
# x2_stats_refs()) regenerates this output from the user's disc image and XML2 install; builds never run this
# script. It stays as history and as the generator of the tracked research copy (the developer-mode input and
# P2's byte-for-byte equivalence reference). Change the stage, not this file.
"""Which XML2 herostat/npcstat names are referenced anywhere else in XML2 (CHRB character lists, any other
XMLB-family attribute value, any .py script string, the exe's string table)? Unreferenced ones are the
safest to drop when the 296-slot stats-name table (XMen2.exe 0x44c1a7: cmp count,0x129) must make room."""
import collections, json, os, re
from common import *

names = {}
for f in ('herostat', 'npcstat'):
    for st in load_xmlb(f'{X2}/Data/{f}.XMLB').iter('stats'):
        names[st.get('name').lower()] = f
refs = collections.defaultdict(set)
idx = x2_index()
for rel, p in idx.items():
    ext = os.path.splitext(rel)[1]
    if rel in ('data/herostat.xmlb', 'data/herostat.engb', 'data/npcstat.xmlb', 'data/npcstat.engb'):
        continue
    if ext in ('.xmlb', '.engb', '.chrb', '.navb', '.boyb', '.pkgb'):
        root = load_xmlb(p)
        for el in root.iter():
            for v in el.attrib.values():
                lv = v.lower()
                if lv in names:
                    refs[lv].add(rel.split('/')[0] + ':' + ext)
    elif ext == '.py':
        for m in re.finditer(r'["\']([^"\'\r\n]{1,40})["\']', open(p, encoding='latin-1').read()):
            lv = m.group(1).lower()
            if lv in names:
                refs[lv].add('scripts:.py')
# package names are derived from stats names: generated/characters/<name>_<skin>.pkgb
pk = collections.Counter(re.match(r'packages/generated/characters/(.+?)_(\d{4,5}|xml)(_nc)?\.pkgb$', r).group(1)
                         for r in idx if re.match(r'packages/generated/characters/(.+?)_(\d{4,5}|xml)(_nc)?\.pkgb$', r))
exe = open(f'{X2}/XMen2.exe', 'rb').read().lower()
out = []
for n, f in sorted(names.items()):
    inexe = (b'\0' + n.encode() + b'\0') in exe
    out.append({'name': n, 'file': f, 'refs': sorted(refs.get(n, [])), 'has_package': pk.get(n, 0), 'in_exe': inexe})
unref = [o for o in out if not o['refs'] and not o['in_exe']]
print(f'{len(names)} XML2 stats names; unreferenced outside herostat/npcstat and exe: {len(unref)}')
for o in unref:
    print(f"  {o['file']:8} {o['name']:28} packages={o['has_package']}")
json.dump(out, open(os.path.join(HERE, 'x2_stats_refs.json'), 'w'), indent=1)
