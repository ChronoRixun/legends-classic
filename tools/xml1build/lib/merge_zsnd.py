"""
Merge two PC ZSND banks: keep every entry of BASE (e.g. XML2's own x_common.zsm) and append the entries of ADD
(e.g. the converted XML1 x_common.zsm) whose sound/track keys BASE does not already have.

    python merge_zsnd.py <base_pc_bank> <add_pc_bank> <out_bank> [--report out.json]

Needed because XML1 and XML2 ship banks with the same file names (x_common, x_voice, menu_a/c and 17 character
banks such as storm_m, cyclop_m, toad_m) -- dropping the XML1 file over XML2's would break XML2's own sounds.
Rules:
  * sounds of ADD whose key is new are appended; their sample/file entries (and audio) are appended and re-indexed
  * tracks of ADD whose key is new are appended; their ZTRK bytecode sound indices (1 byte, controller 0x10 cmd 4)
    are remapped; a sound needed only by such a track but whose key already exists in BASE is appended under a
    private key hash('xml1merge/<bank>/<n>') so it cannot shadow BASE's sound
  * both inputs must be PC banks (convert XML1 banks with convert_zsnd.py first)
"""
import sys, os, json, struct
from . import zsnd, ztrk
from .zhash import elf_hash
from .convert_zsnd import build_pc


def merge(base_path, add_path, out_path):
    A = zsnd.load(base_path, strict=False)
    B = zsnd.load(add_path)
    for bk in (A, B):
        if bk.platform != 'pc':
            raise zsnd.ZsndError('%s is not a PC bank' % bk.path)
    hard = [p for p in A.problems if not p.startswith('~')]
    if hard:
        raise zsnd.ZsndError('base bank has structural problems: %s' % hard)
    base_keys = {h for s in A.sounds for h in s.hashes} | {h for t in A.tracks for h in t.hashes}
    sounds = [(s.hashes, s.raw) for s in A.sounds]
    samples = [(s.hashes, s.raw) for s in A.samples]
    files = [(f.hashes, f.raw, A.file_bytes(f)) for f in A.files]
    tracks = [(t.hashes, t.raw, A.ztrk[i]) for i, t in enumerate(A.tracks)]
    rep = {'base': base_path, 'add': add_path, 'base_sounds': len(A.sounds), 'add_sounds': len(B.sounds),
           'appended_sounds': 0, 'skipped_duplicate_keys': 0, 'appended_tracks': 0, 'private_keys': 0}
    # which ADD sounds are needed
    new_tracks = [i for i, t in enumerate(B.tracks) if t.hashes[0] not in base_keys]
    needed_by_tracks = set()
    for i in new_tracks:
        needed_by_tracks.update(B.ztrk[i][o] for o in ztrk.sound_refs(B.ztrk[i]))
    snd_map, smp_map, file_map = {}, {}, {}
    used_keys = set(base_keys)
    bank_tag = os.path.basename(add_path)
    for s in B.sounds:
        h = s.hashes[0]
        if h in used_keys:
            if s.index not in needed_by_tracks:
                rep['skipped_duplicate_keys'] += 1
                continue
            h = elf_hash('xml1merge/%s/%d' % (bank_tag, s.index))
            rep['private_keys'] += 1
        si = s.u16(0)
        if si not in smp_map:
            smp = B.samples[si]
            fi = smp.u16(0)
            if fi not in file_map:
                f = B.files[fi]
                file_map[fi] = len(files)
                files.append((f.hashes, f.raw, B.file_bytes(f)))
            raw = bytearray(smp.raw)
            struct.pack_into('<H', raw, 0, file_map[fi])
            smp_map[si] = len(samples)
            samples.append((smp.hashes, bytes(raw)))
        raw = bytearray(s.raw)
        struct.pack_into('<H', raw, 0, smp_map[si])
        snd_map[s.index] = len(sounds)
        sounds.append(([h], bytes(raw)))
        used_keys.add(h)
        rep['appended_sounds'] += 1
    for i in new_tracks:
        t = B.tracks[i]
        blob = ztrk.remap(B.ztrk[i], lambda n: snd_map[n])
        tracks.append((t.hashes, t.raw, blob))
        rep['appended_tracks'] += 1
    out = build_pc(sounds, samples, files, tracks)
    with open(out_path, 'wb') as fh:
        fh.write(out)
    # verify
    M = zsnd.load(out_path)
    assert [s.raw for s in M.sounds[:len(A.sounds)]] == [s.raw for s in A.sounds]
    for f in M.files[:len(A.files)]:
        assert M.file_bytes(f) == A.file_bytes(A.files[f.index])
    for i, t in enumerate(M.tracks):
        ztrk.parse(M.ztrk[i])
        assert all(M.ztrk[i][o] < len(M.sounds) for o in ztrk.sound_refs(M.ztrk[i]))
    rep.update({'out': out_path, 'out_sounds': len(M.sounds), 'out_tracks': len(M.tracks), 'out_bytes': len(out)})
    return rep


if __name__ == '__main__':
    a = sys.argv[1:]
    rep = merge(a[0], a[1], a[2])
    print(json.dumps(rep))
    if '--report' in a:
        json.dump(rep, open(a[a.index('--report') + 1], 'w'), indent=1)
