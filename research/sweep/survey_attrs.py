"""Survey attribute names used in XML1 zone XMLs (maps/**/*.eng) with example values,
so path-like references can be resolved to files."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, sys, collections, json
sys.path.insert(0, _REPO + r'/research/sweep')
from sweeplib import parse_text_xml_robust

X1 = _REPO + r'/xml1_loose'
names = collections.defaultdict(collections.Counter)
classes = collections.Counter()
tags = collections.Counter()
for d, _, fs in os.walk(os.path.join(X1, 'maps')):
    for f in fs:
        if not f.endswith('.eng'):
            continue
        root = parse_text_xml_robust(os.path.join(d, f))
        for el in root.iter():
            tags[el.tag] += 1
            if el.tag == 'entity':
                classes[el.get('classname', '')] += 1
            for k, v in el.attrib.items():
                names[(el.tag, k)][v] += 1
print('tags', tags.most_common())
print('classes', classes.most_common())
for (t, k), c in sorted(names.items(), key=lambda x: -sum(x[1].values())):
    if t == 'inst' and k in ('pos', 'orient', 'name', 'classname'):
        continue
    ex = [v for v, _ in c.most_common(4)]
    print('%-10s %-24s %6d %5d  %s' % (t, k, sum(c.values()), len(c), ex))
