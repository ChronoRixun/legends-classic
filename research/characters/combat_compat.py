"""Which XML1 powerstyle/fightstyle constructs does the XML2 engine not know?

 - FightMove handler="ch_*": XML2 exe string table vs XML1 default.xbe string table (handlers are
   registered by name in the exe).
 - trigger name="...": must be a built-in (string in XMen2.exe), an <event name> of the same file, or an
   entry of XML2 shared_combat_events / shared_nodes.
Writes combat_compat.json; prints per-construct usage counts and the XML1 characters affected."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, glob, json, os, re
from common import *


def exe_strings(path):
    d = open(path, 'rb').read()
    return {m.group()[:-1].decode().lower() for m in re.finditer(rb'[\x20-\x7e]{3,}\x00', d)}


x2s = exe_strings(f'{X2}/XMen2.exe')
x1s = exe_strings(_REPO + '/xml1_xbox/default.xbe')
shared = set()
for f in ('shared_combat_events', 'shared_nodes'):
    for el in load_xmlb(f'{X2}/Data/{f}.XMLB').iter():
        if el.get('name'):
            shared.add(el.get('name').lower())
handlers_x2 = {s for s in x2s if s.startswith('ch_')}
handlers_x1 = {s for s in x1s if s.startswith('ch_')}
print('handlers only in XML1 exe:', sorted(handlers_x1 - handlers_x2))

files = [p for p in glob.glob(f'{X1L}/data/powerstyles/*') + glob.glob(f'{X1L}/data/fightstyles/*')
         if p.endswith(('.eng', '.xml'))]
bad_handler = collections.defaultdict(set)
bad_trigger = collections.defaultdict(set)
for p in files:
    root = parse_x1_text(p)
    style = os.path.splitext(os.path.basename(p))[0]
    events = {e.get('name', e.get('Name', '')).lower() for e in root.iter() if e.tag.lower() == 'event'}
    for fm in root.iter():
        h = fm.get('handler')
        if h and h.lower() not in handlers_x2:
            bad_handler[h.lower()].add(style)
        if fm.tag.lower() in ('trigger', 'trigger2'):
            n = (fm.get('name') or fm.get('Name') or '').lower()
            if n and n not in events and n not in shared and n not in x2s:
                bad_trigger[n].add(style)
# which XML1 characters use those styles
users = collections.defaultdict(set)
for f in ('herostat', 'npcstat'):
    for st in parse_x1_text(f'{X1L}/data/{f}.eng').iter('stats'):
        for k in ('powerstyle', 'moveset1'):
            if st.get(k):
                users[st.get(k).lower()].add(st.get('name'))
        for t in st:
            if t.tag.lower() == 'talent' and (t.get('name') or '').lower().startswith('fightstyle_'):
                users[t.get('name').lower()].add(st.get('name'))
out = {'handlers_xml1_only': sorted(handlers_x1 - handlers_x2),
       'unknown_handlers': {h: sorted(s) for h, s in bad_handler.items()},
       'unknown_triggers': {t: sorted(s) for t, s in bad_trigger.items()}}
print('\nFightMove handlers used by XML1 styles but absent from XMen2.exe:')
for h, s in sorted(bad_handler.items()):
    print(f'  {h:28} styles={sorted(s)}  characters={sorted(set().union(*(users.get(x, set()) for x in s)))[:8]}')
print('\ntrigger names used by XML1 styles that XML2 cannot resolve:')
for t, s in sorted(bad_trigger.items(), key=lambda x: -len(x[1])):
    print(f'  {t:28} in {len(s):3} styles e.g. {sorted(s)[:5]}')
json.dump(out, open(os.path.join(HERE, 'combat_compat.json'), 'w'), indent=1)
