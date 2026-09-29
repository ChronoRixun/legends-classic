"""Run verify_conv.check over every converted bank. Audio compared only for banks matching --audio pattern
(suffix list), structure for all."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, json
from multiprocessing import Pool
import verify_conv

XB = _REPO + '/xml1_xbox/sounds/zsds/'
root = sys.argv[1]
audio_ext = tuple(sys.argv[2].split(',')) if len(sys.argv) > 2 else ('.zsm',)


def job(rel):
    try:
        full = rel.endswith(audio_ext)
        r = verify_conv.check(XB + rel, root + rel, max_audio_files=None if full else 0)
        r['rel'] = rel
        return r
    except Exception as e:
        return {'rel': rel, 'problems': ['EXC %r' % e]}


if __name__ == '__main__':
    rels = []
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.endswith(('.zsm', '.zss')):
                rels.append(os.path.relpath(os.path.join(dp, f), root).replace('\\', '/'))
    rels.sort()
    bad = 0
    mins = []
    with Pool(14) as pool:
        for r in pool.imap_unordered(job, rels):
            if r['problems']:
                bad += 1
                print('BAD', r['rel'], r['problems'][:5], flush=True)
            if r.get('snr_min') is not None:
                mins.append((r['snr_min'], r['rel'], r['snr_median']))
    mins.sort()
    print('banks', len(rels), 'bad', bad, 'audio-checked banks', len(mins))
    print('lowest per-bank min SNR:', mins[:5])
    meds = sorted(m[2] for m in mins)
    if meds:
        print('median of bank medians (audio-checked):', meds[len(meds) // 2])
