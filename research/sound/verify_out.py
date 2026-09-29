"""Verify converted PC banks against their XML1 Xbox sources: strict parse, keys/entries/tracks preserved,
sample counts identical, SNR of the decoded PC audio vs the decoded Xbox audio.
Usage: python verify_out.py <converted_root> [only banks listed in a convert log as skipped_existing: --log file]"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, os, json, math
import zsnd, adpcm, ztrk
from multiprocessing import Pool

XB = _REPO + '/xml1_xbox/sounds/zsds'

def check(args):
    out, src = args
    a = zsnd.load(src)
    b = zsnd.load(out)
    assert b.platform == 'pc'
    assert [s.raw for s in b.sounds[:len(a.sounds)]] == [s.raw for s in a.sounds]
    assert [s.hashes for s in b.sounds[:len(a.sounds)]] == [s.hashes for s in a.sounds]
    assert len(a.files) == len(b.files) and len(a.samples) == len(b.samples)
    for i in range(len(a.tracks)):
        assert b.ztrk[i].rstrip(b'\0') == a.ztrk[i].rstrip(b'\0')
        ztrk.parse(b.ztrk[i])
    worst = 1e9
    for fa, fb in zip(a.files, b.files):
        s = next(x for x in a.samples if x.u16(0) == fa.index)
        ch = 2 if s.raw[2] & 2 else 1
        ref, _ = adpcm.xbox_decode(a.file_bytes(fa), ch)
        dec = adpcm.pc_decode(b.file_bytes(fb), ch)
        assert len(dec[0]) == len(ref[0]), (out, fa.index)
        c = adpcm.compare(ref, dec)
        worst = min(worst, c['snr_db'])
    return out, len(a.files), worst

if __name__ == '__main__':
    root = sys.argv[1]
    jobs = []
    only = None
    if '--log' in sys.argv:
        only = set()
        for l in open(sys.argv[sys.argv.index('--log') + 1]):
            try:
                r = json.loads(l)
            except Exception:
                continue
            if r.get('skipped_existing'):
                only.add(os.path.normpath(r['out']))
    for p in zsnd.iter_banks(root):
        if only is not None and os.path.normpath(p) not in only:
            continue
        rel = os.path.relpath(p, root).replace(chr(92), '/')
        jobs.append((p, os.path.join(XB, rel)))
    with Pool(12) as pool:
        for out, n, w in pool.imap_unordered(check, jobs):
            print('OK %-60s files=%4d worstSNR=%.1f' % (out.replace(chr(92), '/').split('/eng/')[-1], n, w), flush=True)
    print('verified', len(jobs))
