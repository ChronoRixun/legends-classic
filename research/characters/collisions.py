# SUPERSEDED (M3 phase 1b, tools/xml1build/SPEC.md 27.7): prepare stage P2 (tools/xml1build/prepare/tables.py,
# collisions()) regenerates this output from the user's disc image and XML2 install; builds never run this
# script. It stays as history and as the generator of the tracked research copy (the developer-mode input and
# P2's byte-for-byte equivalence reference). Change the stage, not this file.
"""Exhaustive path-collision / identity check: every XML1 loose file vs the XML2 install.

For each XML1 file, find the XML2 file that the engine would load for the same logical path
(.igb -> .igb, .xml -> .xmlb, .eng -> .engb (+ .xmlb), .chr -> .chrb, .nav -> .navb, .py -> .py)
and classify:
  identical   - byte-identical (igb) / semantically identical tree (xml) / same text ignoring CR (py)
  collision   - same path, different content
  x1_only     - path not present in XML2
Writes collisions.json (full per-file lists) and prints a summary grouped by category.
"""
import collections, json, os, re
from common import *

TEXT_MAP = {'.xml': ['.xmlb'], '.eng': ['.engb', '.xmlb'], '.chr': ['.chrb'], '.nav': ['.navb']}


def category(rel):
    parts = rel.split('/')
    top = parts[0]
    name = parts[-1]
    if top == 'actors':
        stem = os.path.splitext(name)[0]
        if re.fullmatch(r'\d+', stem):
            return 'actors/skin(numeric)'
        if re.fullmatch(r'\d+_.*', stem):
            return 'actors/animdb(NN_name)'
        return 'actors/other(' + ('fightstyle' if stem.startswith(('fightstyle', 'moveset')) else 'misc') + ')'
    if top == 'hud':
        return 'hud/hud_head' if name.startswith('hud_head_') else 'hud/other'
    if top == 'ui' and len(parts) > 2 and parts[1] in ('hud', 'models') and parts[2] == 'characters':
        return f'ui/{parts[1]}/characters'
    if top in ('data',) and len(parts) > 2:
        return 'data/' + parts[1]
    if top == 'data':
        return 'data/' + os.path.splitext(name)[0]
    if top in ('models', 'effects', 'textures', 'maps', 'scripts') and len(parts) > 2:
        return top + '/' + parts[1]
    return top


def compare(rel, src, idx):
    stem, ext = os.path.splitext(rel)
    if ext in ('.fre', '.ger'):
        return 'skip', None
    if ext in TEXT_MAP:
        for e in TEXT_MAP[ext]:
            dst = idx.get(stem + e)
            if dst:
                try:
                    a = canon(parse_x1_text(src))
                except Exception as ex:
                    return 'x1_parse_error', dst
                b = canon(load_xmlb(dst))
                return ('identical' if a == b else 'collision'), dst
        return 'x1_only', None
    dst = idx.get(rel)
    if not dst:
        return 'x1_only', None
    if ext == '.py':
        a = open(src, 'rb').read().replace(b'\r\n', b'\n')
        b = open(dst, 'rb').read().replace(b'\r\n', b'\n')
        return ('identical' if a == b else 'collision'), dst
    return ('identical' if sha1(src) == sha1(dst) else 'collision'), dst


def main():
    idx = x2_index()
    files = x1_files()
    res = collections.defaultdict(lambda: collections.defaultdict(list))
    for rel, src in sorted(files.items()):
        status, dst = compare(rel, src, idx)
        if status == 'skip':
            continue
        res[category(rel)][status].append(rel)
    json.dump(res, open(os.path.join(HERE, 'collisions.json'), 'w'), indent=1, sort_keys=True)
    tot = collections.Counter()
    print(f'{"category":34} {"x1 files":>8} {"identical":>9} {"collision":>9} {"x1_only":>8} {"parse_err":>9}')
    for cat in sorted(res):
        r = res[cat]
        n = sum(len(v) for v in r.values())
        row = [len(r.get(k, [])) for k in ('identical', 'collision', 'x1_only', 'x1_parse_error')]
        for k, v in zip(('identical', 'collision', 'x1_only', 'x1_parse_error'), row):
            tot[k] += v
        print(f'{cat:34} {n:8} {row[0]:9} {row[1]:9} {row[2]:8} {row[3]:9}')
    print('TOTAL', dict(tot))


if __name__ == '__main__':
    main()
