"""Compare two build output trees (build_xml1.py --out) file by file - the acceptance test of the Sources refactor
and of the prepared-sources mode (BUILDER_DESIGN.md 1.5, phase 1).

    python tools/build_equiv.py <reference_out> <candidate_out> [--map REF_ROOT=CAND_ROOT ...] [--json FILE]

* Every file outside <out>/_build must exist on both sides and be byte-identical (size + sha1).
* <out>/_build: binary files (the media_cache snapshot) byte-identical; JSON files equal after normalisation:
  the timing / time-stamp fields are dropped (TIMING: 'seconds', 'seconds_taken', 'mtime', 'codec', and the
  builder's 'created' / 'finished' / 'verified'), and every
  string has each side's own <out> path replaced by '<OUT>' and every --map root replaced by '<ROOT:i>', so a
  registry 'source' under xml1_loose/ on one side and under a prepared cache's disc/loose/ on the other compare
  equal. Paths are compared case-folded with '/' separators (Windows spellings vary: 'C:\\Games' vs 'c:/games').
  _build/media_cache/movie_verify.json holds [size, mtime_ns] stat keys as values: compared by size only.
* Build logs (*.log) are ignored.

Exit code 0 = equivalent; 1 = differences (listed, first 60)."""
import argparse
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

# + the builder's time stamps (xml1builder: manifest.json 'created', stamp.json 'finished', verify-report.json
# 'verified'); nothing in the pipeline writes these keys
TIMING = ('seconds', 'seconds_taken', 'mtime', 'codec', 'created', 'finished', 'verified')
# the build's own caches (_build/media_cache/*.json, _build/validate_sound_cache.json) key their entries by file stat
# keys [size, mtime_ns]: time stamps too
CACHE_TIMING = TIMING + ('key',)
SKIP_EXT = ('.log',)
# caches whose VALUES are stat-key lists [[size, mtime_ns], ...] (media's movie copy check: source + copy): compared
# by size only - the source's mtime is the time the developer tree or the prepare cache was written
STAT_KEY_VALUES = ('_build/media_cache/movie_verify.json',)
# provenance written only by some modes (build_xml1.py --sources prepared writes _build/sources.json): listed, never
# a difference
PROVENANCE = ('_build/sources.json',)


def files(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root).replace('\\', '/')] = p
    return out


def sha(p):
    h = hashlib.sha1()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _variants(root):
    """spellings of a root as it can appear inside a JSON string: as given, absolute, resolved; '/' and '\\'."""
    out = set()
    for r in (root, os.path.abspath(root), os.path.realpath(root)):
        r = r.rstrip('/\\')
        out.add(r.replace('\\', '/').lower())
    return sorted(out, key=len, reverse=True)


def _norm_str(s, subs):
    s = s.replace('\\\\', '/').replace('\\', '/')     # also repr()'d paths inside messages ('D:\\\\Projects')
    for rx, token in subs:
        s = rx.sub(token, s)
    return s


def normalise(obj, subs, drop=TIMING):
    """drop the `drop` keys; rewrite root paths in strings and dict keys (case-insensitive, '/' separators)."""
    if isinstance(obj, dict):
        return {_norm_str(k, subs): normalise(v, subs, drop) for k, v in obj.items() if k not in drop}
    if isinstance(obj, list):
        return [normalise(v, subs, drop) for v in obj]
    if isinstance(obj, str):
        return _norm_str(obj, subs)
    return obj


def _subs(pairs):
    """[(root spelling, token)] -> [(compiled case-insensitive regex, token)], longest root first; a root matches
    only as a whole path component (followed by '/', the end, or a non-path character)."""
    out = []
    for root, token in sorted(pairs, key=lambda t: len(t[0]), reverse=True):
        out.append((re.compile(re.escape(root) + r'(?=/|$|[^\w.\-])', re.IGNORECASE), token))
    return out


def _sizes_only(rel, obj):
    """STAT_KEY_VALUES files: every value's [size, mtime_ns] pairs reduced to the size."""
    if rel.lower() not in STAT_KEY_VALUES or not isinstance(obj, dict):
        return obj
    return {k: [x[0] if isinstance(x, list) and len(x) == 2 else x for x in v] if isinstance(v, list) else v
            for k, v in obj.items()}


def first_diff(a, b, path=''):
    """a short description of the first place two normalised JSON values differ."""
    if type(a) is not type(b):
        return f'{path or "/"}: {type(a).__name__} vs {type(b).__name__}'
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                return f'{path}/{k}: only on the {"candidate" if k not in a else "reference"} side'
            if a[k] != b[k]:
                return first_diff(a[k], b[k], f'{path}/{k}')
    elif isinstance(a, list):
        if len(a) != len(b):
            return f'{path}: {len(a)} vs {len(b)} items'
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return first_diff(x, y, f'{path}[{i}]')
    elif a != b:
        ra, rb = repr(a), repr(b)
        return f'{path}: {ra[:160]} vs {rb[:160]}'
    return None


def compare(ref, new, maps=()):
    subs_a = [(v, '<OUT>') for v in _variants(ref)]
    subs_b = [(v, '<OUT>') for v in _variants(new)]
    for i, (ra, rb) in enumerate(maps):
        subs_a += [(v, f'<ROOT:{i}>') for v in _variants(ra)]
        subs_b += [(v, f'<ROOT:{i}>') for v in _variants(rb)]
    subs_a, subs_b = _subs(subs_a), _subs(subs_b)
    A = {k: v for k, v in files(ref).items() if not k.lower().endswith(SKIP_EXT)}
    B = {k: v for k, v in files(new).items() if not k.lower().endswith(SKIP_EXT)}
    prov = {k for k in set(A) | set(B) if k.lower() in PROVENANCE}
    res = {'only_ref': sorted(set(A) - set(B) - prov), 'only_new': sorted(set(B) - set(A) - prov), 'differ': [],
           'provenance': sorted(prov), 'files': 0, 'json_meta': 0, 'bytes': 0}
    same_size = []
    for rel in sorted((set(A) & set(B)) - prov):
        pa, pb = A[rel], B[rel]
        meta = rel.split('/', 1)[0].lower() == '_build'
        if meta and rel.lower().endswith('.json'):
            res['json_meta'] += 1
            drop = CACHE_TIMING if 'cache' in rel.lower() else TIMING
            try:
                ja = normalise(_sizes_only(rel, json.load(open(pa, encoding='utf-8'))), subs_a, drop)
                jb = normalise(_sizes_only(rel, json.load(open(pb, encoding='utf-8'))), subs_b, drop)
            except ValueError as e:
                res['differ'].append(f'{rel}: JSON does not parse ({e})')
                continue
            if ja != jb:
                res['differ'].append(f'{rel}: {first_diff(ja, jb)}')
            continue
        res['files'] += 1
        sa, sb = os.path.getsize(pa), os.path.getsize(pb)
        res['bytes'] += sa
        if sa != sb:
            res['differ'].append(f'{rel}: size {sa} vs {sb}')
        else:
            same_size.append((rel, pa, pb, sa))
    # hashing is I/O bound and hashlib releases the GIL: a thread pool
    with ThreadPoolExecutor(max_workers=8) as ex:
        for rel, ok, size in ex.map(lambda t: (t[0], sha(t[1]) == sha(t[2]), t[3]), same_size):
            if not ok:
                res['differ'].append(f'{rel}: content differs (same size {size})')
    res['differ'].sort()
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('ref')
    ap.add_argument('new')
    ap.add_argument('--map', action='append', default=[], metavar='REF_ROOT=CAND_ROOT',
                    help='a source root spelled differently on the two sides (registry "source" values etc.)')
    ap.add_argument('--json', help='write the full result here')
    a = ap.parse_args(argv)
    maps = []
    for m in a.map:
        if '=' not in m:
            ap.error(f'--map {m!r}: expected REF_ROOT=CAND_ROOT')
        maps.append(tuple(m.split('=', 1)))
    res = compare(a.ref, a.new, maps)
    bad = len(res['only_ref']) + len(res['only_new']) + len(res['differ'])
    print(f'{res["files"]} files ({res["bytes"] / 1e9:.2f} GB) and {res["json_meta"]} _build JSON files compared; '
          f'{len(res["only_ref"])} only in reference, {len(res["only_new"])} only in candidate, '
          f'{len(res["differ"])} differ' + (f'; provenance (not compared): {res["provenance"]}' if res['provenance']
                                             else ''))
    shown = 0
    for kind, items in (('only in reference', res['only_ref']), ('only in candidate', res['only_new']),
                        ('differs', res['differ'])):
        for it in items:
            if shown >= 60:
                break
            print(f'  {kind}: {it}')
            shown += 1
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as fh:
            json.dump(res, fh, indent=1)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
