"""exact.py <exe> name... : whole-string (NUL-delimited) matches of each name in the exe, case-sensitive and case-insensitive."""
import sys, re
data = open(sys.argv[1], 'rb').read()
strs = set()
for m in re.finditer(rb'[\x20-\x7e]+', data):
    strs.add(m.group().decode('latin-1'))
low = {}
for s in strs:
    low.setdefault(s.lower(), set()).add(s)
for n in sys.argv[2:]:
    exact = n in strs
    ci = sorted(low.get(n.lower(), set()))
    print(f'{n:28} exact={exact!s:5} ci={ci}')
