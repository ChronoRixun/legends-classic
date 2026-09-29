"""Set an attribute on matching elements of an XMLB file in place.

usage: set_attr.py <file.xmlb> <tag> <match_attr>=<match_value> <attr>=<value>
"""
import sys
import xmlb

path, tag, match, assign = sys.argv[1:5]
mk, mv = match.split('=', 1)
ak, av = assign.split('=', 1)
root = xmlb.decode(open(path, 'rb').read())
n = 0
for el in root.iter(tag):
    if el.get(mk) == mv:
        el.set(ak, av)
        n += 1
open(path, 'wb').write(xmlb.encode(root))
print(f'{n} element(s) updated in {path}')
