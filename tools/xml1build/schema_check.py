"""schema_check - XML1 element/attribute names XMen2.exe can never read (a fixed tools/schema_diff.py).

usage: python tools/xml1build/schema_check.py [--out <build>] [--base "<XML2 folder>"] [--top N]

tools/schema_diff.py matched names as SUBSTRINGS of the lowercased exe bytes, so 'red' counted as present
because of 'zone_shared', 'spark.red' etc. This version matches WHOLE strings, case-insensitively: a name
counts as an exe string only where it is followed by NUL and either preceded by NUL or starts at a 4-byte
aligned address (MSVC .rdata literals are 4-aligned and may follow a non-NUL constant, e.g. 'physent' at
0x682a30). Names XMen2.exe builds at run time ('act' + 'script', ...) are not strings either, so a name that
is also absent from all XML2 retail data is only a candidate - the report lists both facts.

Without --out it scans the XML1 sources (xml1_loose wins over xml1_assets; .fre/.ger skipped). With --out it
scans the XML1-sourced XMLB files the build registered (after every conversion), which is what the game reads.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from xml1build import common as C          # noqa: E402


def exe_strings(base: Path):
    """lowercase whole strings of XMen2.exe and the DLLs next to it."""
    out = set()
    for f in sorted(base.iterdir()):
        if f.suffix.lower() not in ('.exe', '.dll') or C.is_proxy_name(f.name):
            continue
        data = f.read_bytes().lower()
        for m in re.finditer(rb'[\x20-\x7e]{2,}\x00', data):
            s = m.start()
            if s == 0 or data[s - 1] == 0 or s % 4 == 0:
                out.add(m.group()[:-1].decode('latin-1'))
            # a string may also start inside a longer printable run at an aligned offset
            for off in range(s + (-s % 4), m.end() - 2, 4):
                out.add(data[off:m.end() - 1].decode('latin-1'))
    return out


def category(rel):
    parts = rel.split('/')
    return parts[0] if parts[0] != 'data' or len(parts) < 3 else 'data/' + parts[1]


def walk(root, tags, attrs, where):
    for el in root.iter():
        t = el.tag.lower()
        tags[t].add(where)
        for k in el.attrib:
            attrs[(t, k.lower())].add(where)


def scan_x2(base: Path):
    tags, attrs = collections.defaultdict(set), collections.defaultdict(set)
    for dp, dn, fs in os.walk(base):
        dn[:] = [d for d in dn if not C.is_proxy_name(d)]
        for f in fs:
            if f.lower().endswith(('.xmlb', '.engb', '.chrb', '.navb', '.boyb')):
                try:
                    root = C.decode_xmlb((Path(dp) / f).read_bytes())
                except Exception:          # noqa: BLE001
                    continue
                walk(root, tags, attrs, category(C.norm(os.path.relpath(Path(dp) / f, base))))
    return tags, attrs


def scan_x1(ctx):
    tags, attrs = collections.defaultdict(set), collections.defaultdict(set)
    for rel in ctx.x1_rels(''):
        if not rel.endswith(('.xml', '.eng', '.chr', '.nav')) or rel.startswith('packages/'):
            continue
        try:
            root = ctx.read_x1_xml(rel)
        except Exception:                  # noqa: BLE001
            continue
        if root is not None:
            walk(root, tags, attrs, category(rel))
    return tags, attrs


def scan_out(out: Path):
    reg = C.Registry.load(out / '_build/registry.json')
    src = C.Sources.for_out(out)                    # the XML1 trees that build read (SPEC 27)
    roots = tuple(C.norm(p.as_posix()).rstrip('/') + '/' for p in (src.x1_loose, src.x1_assets, src.x1_xbox))
    tags, attrs = collections.defaultdict(set), collections.defaultdict(set)
    for n, e in reg.entries.items():
        if not n.endswith(('.xmlb', '.engb', '.chrb', '.navb')) or not C.norm(e.get('source') or '').startswith(roots):
            continue
        p = out / e['rel']
        try:
            root = C.decode_xmlb(p.read_bytes())
        except Exception:                  # noqa: BLE001
            continue
        walk(root, tags, attrs, category(n))
    return tags, attrs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    ap.add_argument('--base', default=str(C.DEFAULT_BASE))
    ap.add_argument('--top', type=int, default=400)
    ap.add_argument('--json')
    a = ap.parse_args(argv)
    base = Path(a.base)
    strings = exe_strings(base)
    t2, a2 = scan_x2(base)
    if a.out:
        t1, a1 = scan_out(Path(a.out))
        label = f'build {a.out} (XML1-sourced files)'
    else:
        ctx = C.BuildContext(C.REPO_ROOT / 'build/_schema_check', base, scan_out=False,
                             sources=C.Sources.developer(base))
        t1, a1 = scan_x1(ctx)
        label = 'XML1 sources'
    all2 = {k for _, k in a2}
    tags = sorted(t for t in t1 if t not in t2)
    attrs = sorted(p for p in a1 if p not in a2)
    res = {'tags_absent': [], 'attrs_absent': []}
    print(f'{label}: {len(t1)} tags, {len(a1)} tag/attr pairs; XML2 data: {len(t2)} tags, {len(a2)} pairs; '
          f'{len(strings)} whole exe/DLL strings')
    print(f'\n{len(tags)} tags absent from XML2 data ("*" = whole string in XMen2.exe/DLLs):')
    for t in tags:
        flag = '*' if t in strings else ' '
        res['tags_absent'].append({'tag': t, 'exe': t in strings, 'where': sorted(t1[t])[:4]})
        print(f'  {flag} {t:32} {sorted(t1[t])[:4]}')
    dead = [(t, k) for t, k in attrs if k not in strings and k not in all2]
    print(f'\n{len(attrs)} tag.attr pairs absent from XML2 data; {len(dead)} of them are neither an exe/DLL string nor '
          f'used on any XML2 tag (never read unless built at run time) - listed first:')
    shown = 0
    for t, k in sorted(attrs, key=lambda p: (p[1] in strings or p[1] in all2, p)):
        flag = '*' if k in strings else ('~' if k in all2 else ' ')
        res['attrs_absent'].append({'tag': t, 'attr': k, 'exe': k in strings, 'xml2_other_tag': k in all2,
                                    'where': sorted(a1[(t, k)])[:3]})
        if shown < a.top:
            print(f'  {flag} {t}.{k:28} {sorted(a1[(t, k)])[:3]}')
            shown += 1
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
