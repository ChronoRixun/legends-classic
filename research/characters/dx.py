"""dx.py <file.xmlb|pkgb|engb|...> [...] : print decoded Raven binary XML to stdout."""
import sys
from common import xmlb
for p in sys.argv[1:]:
    print(f'== {p}')
    print(xmlb.to_text(xmlb.decode(open(p, 'rb').read())))
