import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, collections
sys.path.insert(0, _REPO + r'/tools')
import xmlb
R = _XML2 + r'/Maps'
vals = collections.Counter()
nfiles = 0
for d, _, fs in os.walk(R):
    for f in fs:
        if f.lower().endswith('.engb') or f.lower().endswith('.xmlb'):
            try:
                r = xmlb.decode(open(os.path.join(d, f), 'rb').read())
            except Exception as e:
                continue
            nfiles += 1
            for e in r.iter():
                for a in ('nextzone', 'prevzone'):
                    if a in e.attrib and e.attrib[a]:
                        v = e.attrib[a]
                        vals[(a, 'full' if '/' in v or '\\' in v else 'short')] += 1
                        if '/' not in v and '\\' not in v:
                            print('short', a, v, os.path.relpath(os.path.join(d, f), R))
print(nfiles, dict(vals))
