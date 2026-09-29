"""Do XML2/XML1 skin IGBs contain their own id as object names ('<id>', '<id>_outline', '<id>_skel')?
Also: re-run the in-place rename feasibility over ALL XML1 numeric IGBs (actors, hud heads, ui) independently."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, struct, sys, collections

X2 = _XML2
X1L = _REPO + '/xml1_loose'


def lp_strings(data, s):
    """occurrences of s+NUL preceded by a plausible u32 padded length"""
    out = []
    for m in re.finditer(re.escape(s.encode()) + b'\x00', data):
        st = m.start()
        if st < 4:
            continue
        (plen,) = struct.unpack_from('<I', data, st - 4)
        if plen % 4 == 0 and len(s) + 1 <= plen <= len(s) + 4:
            out.append((st, plen))
    return out


def scan(dirpath, pat):
    stats = collections.Counter()
    for f in sorted(os.listdir(dirpath)):
        m = re.fullmatch(pat, f, re.I)
        if not m:
            continue
        i = m.group(1)
        d = open(os.path.join(dirpath, f), 'rb').read()
        stats['files'] += 1
        for suf in ('', '_outline', '_skel'):
            if lp_strings(d, i + suf):
                stats['has' + (suf or '_bare')] += 1
    return dict(stats)


print('XML2 Actors', scan(f'{X2}/Actors', r'(\d{4,5})\.igb'))
print('XML1 actors', scan(f'{X1L}/actors', r'(\d{4})\.igb'))

# independent rename-fit check for 4->5 digit (+14000) on every XML1 numeric IGB in actors/hud/ui
roots = [('actors', r'(\d{4})\.igb'), ('hud', r'hud_head_(\d{4})\.igb'), ('ui/hud/characters', r'(\d{4})\.igb'),
         ('ui/models/characters', r'(\d{4})\.igb')]
tot = collections.Counter()
nofit = []
for sub, pat in roots:
    p = os.path.join(X1L, sub)
    if not os.path.isdir(p):
        print('missing', p)
        continue
    for f in os.listdir(p):
        m = re.fullmatch(pat, f, re.I)
        if not m:
            continue
        old = m.group(1)
        new = str(int(old) + 14000)
        d = open(os.path.join(p, f), 'rb').read()
        tot['files'] += 1
        found = False
        for suf in ('', '_outline', '_skel'):
            for st, plen in lp_strings(d, old + suf):
                found = True
                tot['strings'] += 1
                if len(new + suf) + 1 > plen:
                    nofit.append((sub, f, old + suf, plen))
        # any other occurrence of old id as prefix of other names (e.g. 5810_helmet) - left untouched
        others = set(re.findall(re.escape(old.encode()) + rb'_[A-Za-z0-9_]+\x00', d)) - {
            (old + s).encode() + b'\x00' for s in ('_outline', '_skel')}
        if others:
            tot['files_with_subpart_names'] += 1
        if found:
            tot['files_with_names'] += 1
print('XML1 rename check', dict(tot), 'no-fit', nofit[:10])
