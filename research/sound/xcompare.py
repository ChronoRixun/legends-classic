"""Find sounds present (same key) in an XML1 Xbox bank and an XML2 PC bank, decode both, and test which Xbox
block model reproduces the PC waveform (PC headerless IMA is unambiguous). Models:
  A: 64 nibbles/block ; B: header + nibbles[0:63] ; C: header + 64 nibbles (65/block)"""
import sys, math, zsnd, adpcm
from array import array

def xbox_model(data, ch, model):
    outs = [array('h') for _ in range(ch)]
    for blk in adpcm.xbox_blocks(data, ch):
        for c, (pred, idx, res, nibs) in enumerate(blk):
            o = array('h')
            adpcm.decode_nibbles(nibs, pred, min(idx, 88), o)
            if model == 'A':
                outs[c].extend(o)
            elif model == 'B':
                outs[c].append(pred); outs[c].extend(o[:63])
            else:
                outs[c].append(pred); outs[c].extend(o)
    return outs

def best_corr(a, b, maxlag=200, n=None):
    n = n or min(len(a), len(b)) - maxlag
    best = (-2, 0)
    for lag in range(-maxlag, maxlag + 1):
        s = sa = sb = 0.0
        cnt = 0
        for i in range(max(0, -lag), min(n, len(b) - lag, len(a))):
            x = a[i]; y = b[i + lag]
            s += x * y; sa += x * x; sb += y * y
        if sa and sb:
            r = s / math.sqrt(sa * sb)
            if r > best[0]:
                best = (r, lag)
    return best

def main(xp, pp, limit=12):
    xb = zsnd.load(xp); pb = zsnd.load(pp, strict=False)
    pk = {h: s for s in pb.sounds for h in s.hashes}
    done = 0
    for s in xb.sounds:
        h = s.hashes[0]
        if h not in pk or done >= limit:
            continue
        xs = xb.samples[s.u16(0)]; xf = xb.files[xs.u16(0)]
        ps = pb.samples[pk[h].u16(0)]; pf = pb.files[ps.u16(0)]
        xch = 2 if xs.raw[2] & 2 else 1
        pch = 2 if ps.raw[2] & 2 else 1
        if xch != 1 or pch != 1 or xs.u32(4) != ps.u32(4):
            continue
        pcm = adpcm.pc_decode(pb.file_bytes(pf), 1)[0]
        line = '%08x %-28s pc=%6d' % (h, xb.file_name(xf)[:28], len(pcm))
        for m in 'ABC':
            xd = xbox_model(xb.file_bytes(xf), 1, m)[0]
            # correlation over the first ~4000 and a late window
            r1 = best_corr(xd[:3000], pcm[:3000], 64)
            tail0 = max(0, min(len(xd), len(pcm)) - 3000)
            r2 = best_corr(xd[tail0:tail0 + 2500], pcm[tail0:tail0 + 2500], 64) if tail0 > 3000 else (0, 0)
            line += ' | %s len=%6d r0=%.3f@%+d rT=%.3f@%+d' % (m, len(xd), r1[0], r1[1], r2[0], r2[1])
        print(line)
        done += 1

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 12)
