"""Skin-prefix usage in both games: numeric actor/HUD/UI file names and stats skin attributes.
Skin string = %02d/%03d(prefix byte) + %02d(variant) (XMen2.exe 0x4b8090); parser 0x4b9c40 takes
4-5 digit strings, prefix = all but last 2 digits stored in a BYTE."""
import collections, os, re
from common import *

NUM = re.compile(r'^(\d{2,3})(\d{2})$')


def prefixes_from_names(names):
    out = collections.defaultdict(set)
    for n in names:
        m = NUM.match(n)
        if m:
            out[int(m.group(1))].add(n)
    return out


def x2_names():
    idx = x2_index()
    names = set()
    for p in idx:
        for d, pat in (('actors/', r'^actors/(\d{4,5})\.igb$'), ('hud', r'^hud/hud_head_(\d{4,5})\.igb$'),
                       ('ui', r'^ui/(?:hud|models)/characters/(\d{4,5})\.igb$')):
            m = re.match(pat, p)
            if m:
                names.add(m.group(1))
    for f in ('herostat', 'npcstat'):
        for st in load_xmlb(f'{X2}/Data/{f}.XMLB').iter('stats'):
            if st.get('skin'):
                names.add(st.get('skin'))
    return names


def x1_names():
    files = x1_files()
    names = set()
    for p in files:
        for pat in (r'^actors/(\d{4,5})\.igb$', r'^hud/hud_head_(\d{4,5})\.igb$',
                    r'^ui/(?:hud|models)/characters/(\d{4,5})\.igb$'):
            m = re.match(pat, p)
            if m:
                names.add(m.group(1))
    for f in ('herostat', 'npcstat'):
        for st in parse_x1_text(f'{X1L}/data/{f}.eng').iter('stats'):
            if st.get('skin'):
                names.add(st.get('skin'))
    return names


if __name__ == '__main__':
    p2 = prefixes_from_names(x2_names())
    p1 = prefixes_from_names(x1_names())
    print('XML2 prefixes used:', len(p2), sorted(p2))
    print('XML1 prefixes used:', len(p1), sorted(p1))
    free = [p for p in range(256) if p not in p2]
    print('free prefixes (0-255) not used by XML2:', len(free))
    print('  2-digit free:', [p for p in free if p < 100])
    print('  3-digit free:', f'{min(p for p in free if p >= 100)}..255' , len([p for p in free if p >= 100]))
    shared = sorted(set(p1) & set(p2))
    print('XML1 prefixes that XML2 also uses:', len(shared), shared)
    print('XML1 prefixes >= 100:', [p for p in p1 if p >= 100])
