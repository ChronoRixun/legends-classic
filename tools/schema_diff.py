"""List element/attribute names XML1 uses that never appear anywhere in XML2's data or exe."""
import collections, glob, os, re, sys
import xml.etree.ElementTree as ET
import xmlb

X1, X2 = sys.argv[1], sys.argv[2]

def walk(el, tags, attrs, where):
    tags[el.tag.lower()].add(where)
    for k in el.attrib:
        attrs[(el.tag.lower(), k.lower())].add(where)
    for sub in el:
        walk(sub, tags, attrs, where)

def category(rel):
    parts = rel.lower().replace(os.sep, '/').split('/')
    return parts[0] if parts[0] != 'data' or len(parts) < 3 else 'data/' + parts[1]

def load_x1():
    tags, attrs = collections.defaultdict(set), collections.defaultdict(set)
    for f in glob.glob(X1 + '/**/*', recursive=True):
        if os.path.splitext(f)[1].lower() not in ('.xml', '.eng', '.chr', '.nav'):
            continue
        try:
            root = ET.fromstring(b'<r>' + re.sub(rb'<\?xml[^>]*>', b'', open(f, 'rb').read()) + b'</r>')
        except ET.ParseError as e:
            print('parse error', f, e)
            continue
        for el in root:
            walk(el, tags, attrs, category(os.path.relpath(f, X1)))
    return tags, attrs

def load_x2():
    tags, attrs = collections.defaultdict(set), collections.defaultdict(set)
    for f in glob.glob(X2 + '/**/*', recursive=True):
        if not f.lower().endswith(('.xmlb', '.engb', '.chrb', '.navb', '.boyb')):
            continue
        walk(xmlb.decode(open(f, 'rb').read()), tags, attrs, category(os.path.relpath(f, X2)))
    return tags, attrs

t1, a1 = load_x1()
t2, a2 = load_x2()
exe = b''.join(open(os.path.join(X2, f), 'rb').read().lower() for f in os.listdir(X2) if f.lower().endswith(('.exe', '.dll')))
def in_exe(name):
    return name.encode('latin-1') in exe

print(f'XML1: {len(t1)} tags, {len(a1)} tag/attr pairs; XML2: {len(t2)} tags, {len(a2)} pairs')
new_tags = sorted(t for t in t1 if t not in t2)
print(f'\n{len(new_tags)} XML1 tags absent from XML2 data (* = name still found in XML2 exe):')
for t in new_tags:
    print(f"  {'*' if in_exe(t) else ' '} {t:32} {sorted(t1[t])[:4]}")
all2 = {k for _, k in a2}
new_attrs = sorted(p for p in a1 if p not in a2 and p[0] in t2)
print(f'\n{len(new_attrs)} XML1 attrs on shared tags absent from XML2 data:')
for tag, k in new_attrs:
    flag = '*' if in_exe(k) else ('~' if k in all2 else ' ')
    print(f"  {flag} {tag}.{k:28} {sorted(a1[(tag, k)])[:3]}")
