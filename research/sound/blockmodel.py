"""Decide the Xbox ADPCM block model empirically: compare the 'roughness' at block junctions under three models
  A: 64 samples = 64 nibbles, header is only the decoder state (MS Xbox ADPCM wSamplesPerBlock=64)
  B: 64 samples = header sample + nibbles 0..62 (what ffmpeg's adpcm_ima_xbox emits)
  C: 65 samples = header sample + 64 nibbles (MS IMA-ADPCM 0x11 convention)
For each model: mean |x[i+1]-x[i]| over junction pairs vs over all pairs. Also: how often next header == A-state."""
import sys, zsnd, adpcm
from array import array

def analyse(paths, maxfiles=400):
    acc = {'A': [0, 0, 0, 0], 'B': [0, 0, 0, 0], 'C': [0, 0, 0, 0]}  # junction sum, junction n, all sum, all n
    hdr_eq_state = hdr_total = 0
    hdr_vs_last = [0, 0]  # |hdr(N+1) - nib63(N)| , |hdr(N+1) - nib62(N)|
    nf = 0
    for p in paths:
        b = zsnd.load(p)
        for f in b.files:
            if nf >= maxfiles:
                break
            s = next(x for x in b.samples if x.u16(0) == f.index)
            ch = 2 if s.raw[2] & 2 else 1
            data = b.file_bytes(f)
            prev_state = [None] * ch
            prev_blk = [None] * ch
            for blk in adpcm.xbox_blocks(data, ch):
                for c, (pred, idx, res, nibs) in enumerate(blk):
                    out = array('h')
                    st = adpcm.decode_nibbles(nibs, pred, min(idx, 88), out)
                    seqs = {'A': list(out), 'B': [pred] + list(out[:63]), 'C': [pred] + list(out)}
                    for m, seq in seqs.items():
                        a = acc[m]
                        for i in range(len(seq) - 1):
                            a[2] += abs(seq[i + 1] - seq[i]); a[3] += 1
                        if prev_blk[c] is not None:
                            pseq = prev_blk[c][m]
                            j = abs(seq[0] - pseq[-1])
                            a[0] += j; a[1] += 1
                            a[2] += j; a[3] += 1
                    if prev_state[c] is not None:
                        hdr_total += 1
                        if prev_state[c] == (pred, min(idx, 88)):
                            hdr_eq_state += 1
                        hdr_vs_last[0] += abs(pred - prev_blk[c]['A'][-1])
                        hdr_vs_last[1] += abs(pred - prev_blk[c]['A'][-2])
                    prev_state[c] = st
                    prev_blk[c] = seqs
            nf += 1
    print('files analysed:', nf)
    for m, (js, jn, als, aln) in acc.items():
        print('model %s: mean |d| at junction %.1f, overall %.1f, ratio %.2f' % (m, js / jn, als / aln, (js / jn) / (als / aln)))
    print('next header == running state after 64 nibbles: %d / %d' % (hdr_eq_state, hdr_total))
    print('mean |hdr(N+1) - nib63(N)| = %.1f ; |hdr(N+1) - nib62(N)| = %.1f' % (hdr_vs_last[0] / hdr_total, hdr_vs_last[1] / hdr_total))

if __name__ == '__main__':
    analyse(sys.argv[1:])
