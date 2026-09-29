"""Independent Xbox ADPCM block-model check (own decoder, own bank reader).
Finds sounds with identical name-hash in an XML1 Xbox bank and an XML2 PC bank, decodes PC (headerless IMA,
state 0/0, low nibble first -- as disassembled at XMen2.exe 0x616770) and Xbox under models
A (nibbles 0..63), B (hdr + nibbles 0..62), C (hdr + 64 nibbles), and reports lag-0 and best-lag correlation
for the first and last 2000 samples."""
import struct, sys, math, os, subprocess, tempfile, array

STEPS = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97,
         107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
         876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871,
         5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
         27086, 29794, 32767]
IT = [-1, -1, -1, -1, 2, 4, 6, 8]


def step(n, p, i):
    s = STEPS[i]
    d = s >> 3
    if n & 4: d += s
    if n & 2: d += s >> 1
    if n & 1: d += s >> 2
    p = p - d if n & 8 else p + d
    p = max(-32768, min(32767, p))
    i = max(0, min(88, i + IT[n & 7]))
    return p, i


def pc_mono(data):
    p = i = 0
    out = []
    for b in data:
        for n in (b & 15, b >> 4):
            p, i = step(n, p, i)
            out.append(p)
    return out


def xbox_mono(data, model):
    out = []
    for k in range(len(data) // 36):
        blk = data[36 * k:36 * k + 36]
        p = struct.unpack_from('<h', blk, 0)[0]
        i = min(blk[2], 88)
        hdr = p
        dec = []
        for b in blk[4:]:
            for n in (b & 15, b >> 4):
                p, i = step(n, p, i)
                dec.append(p)
        if model == 'A':
            out += dec
        elif model == 'B':
            out += [hdr] + dec[:63]
        else:
            out += [hdr] + dec
    return out


def bank(path):
    d = open(path, 'rb').read()
    pc = d[:8] == b'ZSNDPC  '
    t = [struct.unpack_from('<III', d, 0x10 + 12 * k) for k in range(7)]
    ssz, fsz = (24, 76) if pc else (28, 84)
    snd = {}
    c, ko, eo = t[0]
    for j in range(c):
        h, idx = struct.unpack_from('<II', d, ko + 8 * j)
        si = struct.unpack_from('<H', d, eo + 24 * idx)[0]
        c1, k1, e1 = t[1]
        fi, fl = struct.unpack_from('<HB', d, e1 + ssz * si)
        rate = struct.unpack_from('<I', d, e1 + ssz * si + 4)[0]
        c2, k2, e2 = t[2]
        off, size = struct.unpack_from('<II', d, e2 + fsz * fi)
        snd[h] = (fl, rate, d[off:off + size], d[e2 + fsz * fi + fsz - 64:e2 + fsz * fi + fsz].split(b'\0')[0])
    return snd


def corr(a, b, lag):
    s = sa = sb = 0.0
    for k in range(len(a)):
        j = k + lag
        if 0 <= j < len(b):
            s += a[k] * b[j]; sa += a[k] * a[k]; sb += b[j] * b[j]
    return s / math.sqrt(sa * sb) if sa and sb else 0


def best(a, b, maxlag=40):
    return max((corr(a, b, l), l) for l in range(-maxlag, maxlag + 1))


if __name__ == '__main__':
    xb = bank(sys.argv[1])
    pb = bank(sys.argv[2])
    lim = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    n = 0
    for h, (fl, rate, data, nm) in xb.items():
        if h not in pb or fl & 2:
            continue
        pfl, prate, pdata, pnm = pb[h]
        if pfl & 2 or prate != rate:
            continue
        pcm = pc_mono(pdata)
        if len(pcm) < 5000:
            continue
        line = '%08x %-24s pc=%6d' % (h, nm.decode()[:24], len(pcm))
        for m in 'ABC':
            x = xbox_mono(data, m)
            L = min(len(x), len(pcm))
            r0 = corr(x[:2000], pcm[:2000], 0)
            bh = best(x[:2000], pcm[:2000])
            bt = best(x[L - 2000:L], pcm[L - 2000:L])
            line += ' | %s n=%6d r0=%.4f best=%.4f@%+d tail=%.4f@%+d' % (m, len(x), r0, bh[0], bh[1], bt[0], bt[1])
        print(line)
        n += 1
        if n >= lim:
            break
