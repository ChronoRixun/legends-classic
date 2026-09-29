"""Test helper: put XML2's original attributes back on the XML2 entries of a built zoneinfo.

usage: restore_zoneinfo_x2attrs.py <build_dir>
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xmlb

import local_paths  # noqa: E402
XML2 = local_paths.xml2_dir() + '/Data/'
build = sys.argv[1]
for name in ('zoneinfo.XMLB', 'zoneinfo.engb'):
    orig = {z.get('name'): z for z in xmlb.decode(open(XML2 + name, 'rb').read())}
    path = os.path.join(build, 'Data', name)
    root = xmlb.decode(open(path, 'rb').read())
    restored = 0
    for z in root:
        o = orig.get(z.get('name'))
        if o is not None and dict(o.attrib) != dict(z.attrib):
            z.attrib = dict(sorted(o.attrib.items()))
            restored += 1
    open(path, 'wb').write(xmlb.encode(root))
    print(name, 'restored', restored, 'entries')
