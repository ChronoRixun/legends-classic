"""Compare two outputs of the sound stages (convert_zsnd --batch, merge_all, fix_music fix) file by file.

    python tools/sound_equiv.py <reference_root> <candidate_root> [--map REF_INPUT=NEW_INPUT ...]

Each root holds the outputs of the three stages (e.g. all_ima/eng, merged/eng, music/eng); every bank must be
byte-identical and present on both sides. The JSON reports (_convert_report.json, _merge_report.json,
_fix_music_report.json) must be equal after replacing each root's path by a placeholder and dropping the timing
fields ('seconds', 'seconds_taken') and the encoder backend ('codec': compiled kernel or numpy - comparing the two
is the point). --map also maps an input root that differs between the runs (e.g. the sounds/zsds of a prepared
cache vs xml1_xbox/sounds/zsds): in the candidate's reports NEW_INPUT reads as REF_INPUT. Exit code 0 = equivalent."""
import hashlib, json, os, sys

REPORTS = ('_convert_report.json', '_merge_report.json', '_fix_music_report.json')
TIMING = ('seconds', 'seconds_taken', 'codec')


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


def norm(obj, roots):
    if isinstance(obj, dict):
        return {k: norm(v, roots) for k, v in obj.items() if k not in TIMING}
    if isinstance(obj, list):
        return [norm(v, roots) for v in obj]
    if isinstance(obj, str):
        s = obj.replace('\\', '/')
        for r in roots:
            s = s.replace(r, '<ROOT>')
        return s
    return obj


def remap(obj, maps):
    """the candidate's input roots read as the reference's (maps: [(ref_root, new_root)], '/' separators)."""
    if not maps:
        return obj
    if isinstance(obj, dict):
        return {k: remap(v, maps) for k, v in obj.items()}
    if isinstance(obj, list):
        return [remap(v, maps) for v in obj]
    if isinstance(obj, str):
        s = obj.replace('\\', '/')
        for a, b in maps:
            s = s.replace(b, a)
        return s
    return obj


def main(ref, new, maps=()):
    ref_roots = [os.path.abspath(ref).replace('\\', '/'), ref.replace('\\', '/')]
    new_roots = [os.path.abspath(new).replace('\\', '/'), new.replace('\\', '/')]
    A, B = files(ref), files(new)
    bad = []
    only_a = sorted(set(A) - set(B))
    only_b = sorted(set(B) - set(A))
    skip = {'convert.log', 'merge.log', 'music.log'}
    only_a = [r for r in only_a if os.path.basename(r) not in skip]
    only_b = [r for r in only_b if os.path.basename(r) not in skip]
    bad += ['missing in candidate: ' + r for r in only_a] + ['extra in candidate: ' + r for r in only_b]
    banks = reports = 0
    for rel in sorted(set(A) & set(B)):
        base = os.path.basename(rel)
        if base in skip:
            continue
        if base in REPORTS:
            ra = norm(json.load(open(A[rel])), ref_roots)
            rb = norm(remap(json.load(open(B[rel])), maps), new_roots)
            reports += 1
            if ra != rb:
                n = sum(1 for x, y in zip(ra, rb) if x != y) if isinstance(ra, list) else 1
                bad.append(f'report differs: {rel} ({n} entries)')
            continue
        banks += 1
        if os.path.getsize(A[rel]) != os.path.getsize(B[rel]) or sha(A[rel]) != sha(B[rel]):
            bad.append('bank differs: ' + rel)
    print(f'{banks} banks and {reports} reports compared; {len(bad)} problem(s)')
    for b in bad[:50]:
        print('  ' + b)
    return 1 if bad else 0


if __name__ == '__main__':
    args, maps = [], []
    it = iter(sys.argv[1:])
    for x in it:
        if x == '--map':
            a, b = next(it).split('=', 1)
            maps.append((a.replace('\\', '/'), b.replace('\\', '/')))
        else:
            args.append(x)
    sys.exit(main(args[0], args[1], maps))
