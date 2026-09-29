"""Equivalence check of the prepare stages against today's hand-made inputs (BUILDER_DESIGN.md 1.5: "equivalence is
the acceptance test").

    python tools/prepare_equiv.py --disc <cache>/<disc_id>/disc [--tables <cache>/<disc_id>/prepared/tables-...]
                                  [--root <repo>] [--json FILE]

P1 disc: loose/ vs xml1_loose/, assets/ vs xml1_assets/, xbox/ vs xml1_xbox/ - every file present on both sides
must be byte-identical (size + sha1); a file present on one side only is listed with the rule that explains it
(prepare.disc.expected_one_sided) or as UNEXPECTED.
P2 tables: each output vs its research copy - byte-identical, else JSON-equal (only the line ends / key order
differ), else the differences; missions/*.xml vs research/scripts/out/data/missions/*.xml; names_xml1's ambiguous
keys (the candidate order decided the name) are listed with the name the research copy has.

Exit code 0 = equivalent (every one-sided file explained, every table equal or explained), 1 = otherwise."""
import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xml1build.prepare import disc as P1, tables as P2  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def files(root: Path):
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


def compare_tree(ref: Path, new: Path, rules):
    A, B = files(ref), files(new)
    res = {'ref': str(ref), 'new': str(new), 'ref_files': len(A), 'new_files': len(B), 'identical': 0,
           'bytes': 0, 'differ': [], 'only_ref': {}, 'only_new': {}, 'unexplained': []}
    pairs = []
    for rel in sorted(set(A) & set(B)):
        sa, sb = os.path.getsize(A[rel]), os.path.getsize(B[rel])
        if sa != sb:
            res['differ'].append(f'{rel}: size {sa} vs {sb}')
        else:
            pairs.append((rel, A[rel], B[rel], sa))
    with ThreadPoolExecutor(max_workers=8) as ex:
        for rel, ok, size in ex.map(lambda t: (t[0], sha(t[1]) == sha(t[2]), t[3]), pairs):
            if ok:
                res['identical'] += 1
                res['bytes'] += size
            else:
                res['differ'].append(f'{rel}: content differs')
    for side, rels in (('only_ref', sorted(set(A) - set(B))), ('only_new', sorted(set(B) - set(A)))):
        for rel in rels:
            why = next((w for fn, w in rules if side == 'only_ref' and fn(rel)), None)
            if why is None:
                res['unexplained'].append(f'{side}: {rel}')
                why = 'UNEXPECTED'
            res[side].setdefault(why, []).append(rel)
    return res


def _json(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def compare_tables(tables: Path, root: Path):
    out = {'files': [], 'problems': []}
    for rel, name in P2.OUTPUTS.items():
        a, b = root / 'research' / rel, tables / name
        row = {'research': rel, 'prepared': name}
        if not a.is_file() or not b.is_file():
            row['result'] = 'missing ' + ('research copy' if not a.is_file() else 'prepared output')
            out['problems'].append(f'{rel}: {row["result"]}')
        elif a.read_bytes() == b.read_bytes():
            row['result'] = 'byte-identical'
        elif a.read_bytes().replace(b'\r\n', b'\n') == b.read_bytes().replace(b'\r\n', b'\n'):
            row['result'] = 'identical but for line ends'
        elif _json(a) == _json(b):
            row['result'] = 'JSON-equal (formatting / key order differs)'
        else:
            row['result'] = 'DIFFERENT'
            row['diff'] = describe_json_diff(_json(a), _json(b))
            if rel != 'sound/names_xml1.json':
                out['problems'].append(f'{rel}: {row["diff"][:3]}')
        out['files'].append(row)
    # the planned mission text files (P3 compiles them)
    mref = root / 'research' / 'scripts' / 'out' / 'data' / 'missions'
    mnew = tables / P2.MISSIONS_DIR
    names = sorted({p.name for p in mref.glob('*.xml')} | {p.name for p in mnew.glob('*.xml')})
    same = [n for n in names if (mref / n).is_file() and (mnew / n).is_file() and
            (mref / n).read_bytes() == (mnew / n).read_bytes()]
    out['missions'] = {'files': len(names), 'byte_identical': len(same),
                       'differ': [n for n in names if n not in same]}
    if out['missions']['differ']:
        out['problems'].append(f'mission texts differ: {out["missions"]["differ"]}')
    # names_xml1: the ambiguous keys (explained, not problems, when the research copy took one of the candidates)
    st = json.loads((tables / 'stage.json').read_text(encoding='utf-8'))
    ref_names = _json(root / 'research' / 'sound' / 'names_xml1.json')
    new_names = _json(tables / 'names_xml1.json')
    amb = []
    for bank, key, cands in st.get('ambiguous_sound_keys', []):
        r = ref_names.get(bank, {}).get(key)
        n = new_names.get(bank, {}).get(key)
        amb.append({'bank': bank, 'key': key, 'candidates': cands, 'research': r, 'prepared': n,
                    'same': r == n, 'research_in_candidates': r in cands})
    out['names_ambiguous'] = amb
    # every names difference must be an ambiguous key where the research copy took another candidate
    amb_keys = {(x['bank'], x['key']) for x in amb if x['research_in_candidates']}
    unexplained = []
    for bank in sorted(set(ref_names) | set(new_names)):
        ra, rb = ref_names.get(bank, {}), new_names.get(bank, {})
        for key in sorted(set(ra) | set(rb)):
            if ra.get(key) != rb.get(key) and (bank, key) not in amb_keys:
                unexplained.append((bank, key, ra.get(key), rb.get(key)))
    out['names_unexplained'] = unexplained
    if unexplained:
        out['problems'].append(f'names_xml1: {len(unexplained)} unexplained differences, e.g. {unexplained[:3]}')
    return out


def describe_json_diff(a, b, path='', out=None, limit=20):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f'{path}/{k}: only in {"prepared" if k not in a else "research"}')
            elif a[k] != b[k]:
                describe_json_diff(a[k], b[k], f'{path}/{k}', out, limit)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                describe_json_diff(x, y, f'{path}[{i}]', out, limit)
    else:
        out.append(f'{path}: {str(a)[:100]} vs {str(b)[:100]}')
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--disc', required=True, help="P1's published directory (<cache>/<disc_id>/disc)")
    ap.add_argument('--tables', help="P2's published directory (default: the newest under <disc>/../prepared)")
    ap.add_argument('--root', default=str(ROOT), help='the repo with the hand-made xml1_* folders and research/')
    ap.add_argument('--json', help='write the full result here')
    a = ap.parse_args(argv)
    disc, root = Path(a.disc), Path(a.root)
    rules = P1.expected_one_sided()
    result = {'disc': {}, 'tables': None}
    ok = True
    for mine, theirs in ((P1.LOOSE, 'xml1_loose'), (P1.ASSETS, 'xml1_assets'), (P1.XBOX, 'xml1_xbox')):
        r = compare_tree(root / theirs, disc / mine, rules[theirs])
        result['disc'][mine] = r
        print(f'P1 {mine + "/":8} vs {theirs + "/":13}: {r["identical"]} files byte-identical '
              f'({r["bytes"] / 1e6:.0f} MB), {len(r["differ"])} differ; one side only: '
              f'{sum(len(v) for v in r["only_ref"].values())} in {theirs}, '
              f'{sum(len(v) for v in r["only_new"].values())} in {mine}')
        for side, label in (('only_ref', theirs), ('only_new', mine)):
            for why, rels in r[side].items():
                print(f'    only in {label}: {len(rels):4}  {why}  (e.g. {rels[0]})')
        for d in r['differ'][:10]:
            print(f'    DIFFERS: {d}')
        ok &= not r['differ'] and not r['unexplained']
    tables = Path(a.tables) if a.tables else None
    if tables is None:
        cands = sorted((disc.parent / 'prepared').glob(f'{P2.STAGE}-v*'), key=lambda p: p.stat().st_mtime)
        cands = [c for c in cands if not c.name.endswith('.partial')]
        tables = cands[-1] if cands else None
    if tables is not None:
        t = compare_tables(tables, root)
        result['tables'] = t
        for row in t['files']:
            print(f'P2 {row["prepared"]:19} vs research/{row["research"]}: {row["result"]}')
            for d in row.get('diff', [])[:5]:
                print(f'    {d}')
        m = t['missions']
        print(f'P2 missions/*.xml       vs research/scripts/out/data/missions: {m["byte_identical"]}/{m["files"]} '
              f'byte-identical' + (f'; differ: {m["differ"]}' if m['differ'] else ''))
        amb = t['names_ambiguous']
        print(f'P2 names_xml1 ambiguous keys (candidate order decides the name): {len(amb)}, '
              f'{sum(1 for x in amb if x["same"])} named as in the research copy, '
              f'{sum(1 for x in amb if not x["same"] and x["research_in_candidates"])} the research copy took another '
              f'candidate; unexplained differences: {len(t["names_unexplained"])}')
        for x in amb[:12]:
            print(f'    {x["bank"]} {x["key"]}: research {x["research"]!r}, prepared {x["prepared"]!r} '
                  f'(candidates {x["candidates"]})')
        for p in t['problems']:
            print(f'    PROBLEM: {p}')
        ok &= not t['problems']
    else:
        print('P2: no tables directory given or found')
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=1), encoding='utf-8')
    print('EQUIVALENT' if ok else 'NOT EQUIVALENT')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
