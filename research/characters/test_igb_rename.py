"""Dry-run x1names.igb_rename over every XML1 file named by a skin id (actors/, hud/, ui/*/characters/):
counts renamed strings, reports any that would not fit, and checks that no other bytes change."""
import os, re
from common import *
from x1names import igb_rename, map_skin

files = x1_files()
tot = fit = 0
bad = []
zero = []
for rel, p in sorted(files.items()):
    m = re.fullmatch(r'(?:actors/|hud/hud_head_|ui/(?:hud|models)/characters/)(\d{4})\.igb', rel)
    if not m:
        continue
    old = m.group(1)
    data = open(p, 'rb').read()
    new, n, problems = igb_rename(data, old, map_skin(old))
    assert len(new) == len(data)
    diff = sum(1 for a, b in zip(data, new) if a != b)
    tot += 1
    if problems:
        bad.append((rel, problems))
    if n == 0:
        zero.append(rel)
    else:
        fit += 1
print(f'{tot} skin-named IGBs; renamed>=1 string in {fit}; no matching string in {len(zero)}; unfit {len(bad)}')
for rel, pr in bad:
    print('  UNFIT', rel, pr[:4])
print('  no-name files (first 20):', zero[:20])
