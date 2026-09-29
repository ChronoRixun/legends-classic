"""
Numpy implementations of the adpcm.py codecs that give BIT-IDENTICAL results to the pure-Python reference
functions (adpcm.*_py) and to xml1build.lib.fix_music.beam_window, only much faster.

Decoders
  xbox_decode_np : every Xbox block restarts from its header, so all blocks decode in lockstep (63 vector steps).
  pc_decode_np   : one continuous IMA stream from (0,0). Both state updates are "clamped adds",
                   x' = min(max(x + a, lo), hi), and clamped adds compose into clamped adds, so the step index and
                   then the predictor are computed with a blocked scan (compose each block, chain the block
                   functions, replay the blocks in lockstep). Exact integer arithmetic throughout.

Encoders: greedy (encode_samples_py, search=True), beam width 4 x 3 candidates (encode_beam_py), the weighted
64-wide beam of fix_music.beam_window.
  IMA encoding is sequential: sample t needs the decoder state after sample t-1. The streams are cut into units
  (encode_beam restarts its beam every 1024 samples from the single committed state, so its windows are natural
  units; the greedy encoder is cut anywhere; a beam_window call is one unit). A unit's result depends only on its
  samples and its start state (pred, idx), so units run side by side as numpy "lanes": many files / channels in
  lockstep, and along one long stream speculatively from GUESSED start states (solve_chains); a unit counts only
  once it was run from the true end state of its predecessor, so the result is the sequential one whatever the
  guesses were. The lane kernels reproduce the reference tie-breaking exactly (greedy: the lower candidate wins
  ties; beam: dict insertion order + stable sort; wide beam: the reference's own np.argpartition order).
"""
import math
import numpy as np
from . import adpcm

_I64 = np.int64
NSTEP = 89
OFF = 1 << 18                      # row offset of the global sorted-diff table (|diff| < 2^17)
SDF = np.array([d for row in adpcm.SORTED_D for d in row], dtype=_I64)            # sorted diff per (idx, rank)
SNF = np.array([n for row in adpcm.SORTED_N for n in row], dtype=_I64)            # nibble per (idx, rank)
SD_G = SDF + np.repeat(np.arange(NSTEP, dtype=_I64) * OFF, 16)                   # globally sorted
DIFFF = np.array([d for row in adpcm.DIFF for d in row], dtype=_I64)             # (idx*16 + nibble) -> diff
NEXTF = np.array([n for row in adpcm.NEXT for n in row], dtype=_I64)             # (idx*16 + nibble) -> next idx
CNX = NEXTF[np.repeat(np.arange(NSTEP, dtype=_I64) * 16, 16) + SNF]               # (idx, rank) -> next idx
IDXF = np.array(adpcm.IDX, dtype=_I64)
STEPS_NP = np.array(adpcm.STEPS, dtype=_I64)
J3 = np.arange(3, dtype=_I64)
BIG = 1 << 62
M18 = (1 << 18) - 1


def _clamp(x, lo, hi):
    np.maximum(x, lo, out=x)
    np.minimum(x, hi, out=x)
    return x


# ---------------------------------------------------------------- scans / decoders

def clamp_scan(a, lo, hi, x0, block=None):
    """x[0] = x0, x[t+1] = min(max(x[t] + a[t], lo), hi); returns x[1..N] (int64)."""
    a = np.asarray(a, dtype=_I64)
    n = len(a)
    if n == 0:
        return np.zeros(0, dtype=_I64)
    if block is None:
        block = max(64, int(math.sqrt(n)) & ~7)
    nb = -(-n // block)
    aa = np.zeros(nb * block, dtype=_I64)                 # padding: adds 0, harmless after the end
    aa[:n] = a
    at = np.ascontiguousarray(aa.reshape(nb, block).T)    # (block, nb): row t = step t of every block
    # compose each block into one clamped add (A, L, H): x -> min(max(x + A, L), H); the first step alone is
    # (a0, lo, hi), then (A, L, H) o step = (A + s, clamp(L + s), clamp(H + s))
    A = at[0].copy()
    L = np.full(nb, lo, dtype=_I64)
    H = np.full(nb, hi, dtype=_I64)
    for t in range(1, block):
        s = at[t]
        A += s
        L += s
        _clamp(L, lo, hi)
        H += s
        _clamp(H, lo, hi)
    starts = [0] * nb                                     # chain the block functions (nb python steps)
    x = int(x0)
    Al, Ll, Hl = A.tolist(), L.tolist(), H.tolist()
    for k in range(nb):
        starts[k] = x
        x += Al[k]
        if x < Ll[k]:
            x = Ll[k]
        elif x > Hl[k]:
            x = Hl[k]
    X = np.array(starts, dtype=_I64)
    out = np.empty((block, nb), dtype=_I64)
    for t in range(block):
        X += at[t]
        _clamp(X, lo, hi)
        out[t] = X
    return out.T.reshape(-1)[:n]


def nibbles_pc(data, channels):
    """PC headerless IMA bytes -> per-channel nibble arrays (uint8)."""
    b = np.frombuffer(bytes(data), dtype=np.uint8)
    if channels == 1:
        n = np.empty(2 * len(b), dtype=np.uint8)
        n[0::2] = b & 15
        n[1::2] = b >> 4
        return [n]
    return [b & 15, b >> 4]


CHUNK = 1 << 20                    # samples per piece in the decoders / compare (bounds the temporaries)


def ima_decode_nibbles(nibs, pred=0, idx=0, out=None):
    """Continuous IMA decode of a nibble array from state (pred, idx) -> samples (one per nibble; int64, or written
    into `out`). Decoded in pieces of CHUNK nibbles, each from the state the previous piece ended in."""
    nibs = np.asarray(nibs)
    if out is None:
        out = np.empty(len(nibs), dtype=_I64)
    for a in range(0, len(nibs), CHUNK):
        nb = nibs[a:a + CHUNK].astype(_I64)
        ix = clamp_scan(IDXF[nb & 7], 0, 88, idx)                 # index AFTER each nibble
        before = np.empty(len(nb), dtype=_I64)
        before[0] = idx
        before[1:] = ix[:-1]
        x = clamp_scan(DIFFF[before * 16 + nb], -32768, 32767, pred)
        out[a:a + len(nb)] = x
        pred, idx = int(x[-1]), int(ix[-1])
    return out


def pc_decode_np(data, channels):
    """== adpcm.pc_decode_py, as an int16 array (channels, n)."""
    nibs = nibbles_pc(data, channels)
    out = np.empty((channels, len(nibs[0])), dtype=np.int16)
    for c, n in enumerate(nibs):
        ima_decode_nibbles(n, out=out[c])
    return out


def xbox_decode_np(data, channels):
    """== adpcm.xbox_decode_py: (int16 array (channels, n), stats)."""
    bs = 36 * channels
    nblk = len(data) // bs
    stats = {'blocks': nblk, 'bad_idx': 0, 'reserved_nonzero': 0, 'hdr_state_mismatch': 0,
             'tail_bytes': len(data) % bs}
    if nblk == 0:
        return np.zeros((channels, 0), dtype=np.int16), stats
    raw = np.frombuffer(bytes(data[:nblk * bs]), dtype=np.uint8).reshape(nblk, bs)
    h = raw[:, :4 * channels].reshape(nblk, channels, 4).astype(_I64)
    pred = h[..., 0] | (h[..., 1] << 8)
    pred = np.where(pred >= 32768, pred - 65536, pred)
    idx = h[..., 2].copy()
    bad = idx > 88
    stats['bad_idx'] = int(bad.sum())
    idx[bad] = 88
    stats['reserved_nonzero'] = int((h[..., 3] != 0).sum())
    # body: 8 words x channels x 4 bytes, low nibble first -> per channel 64 nibbles (the last one is not played)
    out = np.empty((channels, nblk, 64), dtype=np.int16)
    pe = np.empty((channels, nblk), dtype=_I64)            # decoder state after each block's 63 played nibbles
    ie = np.empty((channels, nblk), dtype=_I64)
    step = max(1, CHUNK // 64)
    for b0 in range(0, nblk, step):
        b1 = min(nblk, b0 + step)
        body = raw[b0:b1, 4 * channels:].reshape(b1 - b0, 8, channels, 4).transpose(2, 1, 3, 0)
        body = body.reshape(channels, 32, b1 - b0)
        nib = np.empty((channels, 64, b1 - b0), dtype=np.uint8)
        nib[:, 0::2] = body & 15
        nib[:, 1::2] = body >> 4
        o = np.empty((channels, 64, b1 - b0), dtype=np.int16)
        p, i = pred[b0:b1].T.copy(), idx[b0:b1].T.copy()   # (channels, blocks)
        o[:, 0] = p
        for t in range(63):
            k = i * 16 + nib[:, t]
            p += DIFFF[k]
            _clamp(p, -32768, 32767)
            i = NEXTF[k]
            o[:, t + 1] = p
        out[:, b0:b1] = o.transpose(0, 2, 1)
        pe[:, b0:b1] = p
        ie[:, b0:b1] = i
    if nblk > 1:                                          # header vs the previous block's decoder state
        stats['hdr_state_mismatch'] = int(((pe[:, :-1] != pred.T[:, 1:]) | (ie[:, :-1] != idx.T[:, 1:])).sum())
    return out.reshape(channels, nblk * 64), stats


def pack_np(nib_chans):
    """== adpcm.pc_pack_py."""
    if len(nib_chans) == 1:
        n = np.asarray(nib_chans[0], dtype=np.uint8)
        if len(n) & 1:
            n = np.concatenate([n, np.zeros(1, dtype=np.uint8)])
        return (n[0::2] | (n[1::2] << 4)).astype(np.uint8).tobytes()
    l, r = (np.asarray(c, dtype=np.uint8) for c in nib_chans)
    assert len(l) == len(r)
    return (l | (r << 4)).astype(np.uint8).tobytes()


def compare_np(a_chans, b_chans):
    """== adpcm.compare_py (exact integer sums, the same float formula)."""
    n = min(len(a_chans[0]), len(b_chans[0]))
    sig = err = exact = maxe = 0
    for a, b in zip(a_chans, b_chans):
        a, b = np.asarray(a), np.asarray(b)
        for s in range(0, n, CHUNK):
            e = min(n, s + CHUNK)
            x = a[s:e].astype(_I64)
            d = x - b[s:e].astype(_I64)
            sig += int(np.dot(x, x))
            err += int(np.dot(d, d))
            exact += int(np.count_nonzero(d == 0))
            maxe = max(maxe, int(np.abs(d).max()))
    tot = n * len(a_chans)
    snr = 10 * math.log10(sig / err) if err else float('inf')
    return {'n': n, 'exact_pct': round(100 * exact / tot, 3), 'snr_db': round(snr, 2), 'max_err': maxe}


# ---------------------------------------------------------------- lane kernels
# All kernels take the samples time-major, XT (T, lanes), lanes sorted by length (descending), so the lanes still
# running at step t are a prefix [:act[t]] and every numpy inner loop runs over lanes. They return the nibbles
# time-major (T, lanes) uint8 plus the end state of every lane.

def _active_counts(lens, T):
    """act[t] = number of lanes with len > t (lens sorted descending)."""
    return np.searchsorted(-np.asarray(lens, dtype=_I64), -np.arange(T, dtype=_I64), side='left')


def _greedy_table():
    """(idx, bisect position k) -> the two candidates encode_samples_py tries (ranks k-1 and k; only rank 0 for
    k = 0 and only rank 15 for k = 16, stored twice). Packed: nibble1 | next1 << 4 | nibble2 << 11 | next2 << 15 |
    (diff1 + 2^17) << 22 | (diff2 + 2^17) << 40, so candidate 2's (nibble, next) = candidate 1's shifted by 11."""
    t = np.zeros(NSTEP * 17, dtype=_I64)
    for r in range(NSTEP):
        for k in range(17):
            j1 = 0 if k == 0 else 15 if k == 16 else k - 1
            j2 = 0 if k == 0 else 15 if k == 16 else k
            a, b = r * 16 + j1, r * 16 + j2
            t[r * 17 + k] = (int(SNF[a]) | int(CNX[a]) << 4 | int(SNF[b]) << 11 | int(CNX[b]) << 15 |
                             (int(SDF[a]) + (1 << 17)) << 22 | (int(SDF[b]) + (1 << 17)) << 40)
    return t


GT = _greedy_table()


def _greedy_lanes(XT, lens, P0, I0):
    """Greedy nearest-reconstruction IMA encoder (== adpcm.encode_samples_py(search=True)) on independent lanes:
    the reconstruction nearest the target among the two around the bisect position, the lower one on a tie."""
    T, L = XT.shape
    P = np.array(P0, dtype=_I64)
    I = np.array(I0, dtype=_I64)
    OUT = np.zeros((T, L), dtype=np.uint8)
    act = _active_counts(lens, T)
    for t in range(T):
        A = act[t]
        if A == 0:
            break
        s = XT[t, :A]
        p, i = P[:A], I[:A]
        q = np.searchsorted(SD_G, (s - p) + i * OFF)          # = i * 16 + bisect_left(row i, s - p)
        q += i
        Q = GT[q]
        pb = p - (1 << 17)
        p1 = _clamp(((Q >> 22) & M18) + pb, -32768, 32767)
        p2 = _clamp((Q >> 40) + pb, -32768, 32767)
        take2 = np.abs(p2 - s) < np.abs(p1 - s)
        F = np.where(take2, Q >> 11, Q)
        P[:A] = np.where(take2, p2, p1)
        OUT[t, :A] = F & 15
        I[:A] = (F >> 4) & 127
    return OUT, P, I


TAB = ((SDF + (1 << 17)) << 12) | (CNX << 4) | SNF          # (idx, rank) -> diff | next idx | nibble, packed
EINV = 1 << 56                                                # error of an empty beam slot (> any real error)
LO_TAB = np.clip(np.arange(17, dtype=_I64) - 1, 0, 13)      # bisect position k -> first of the 3 ranks
PI6 = np.array([0, 0, 0, 1, 1, 2])
PJ6 = np.array([1, 2, 3, 2, 3, 3])
C12 = np.arange(12, dtype=_I64)[:, None]
J3C = J3[None, :, None]


def _beam4_exact_rows(key, e, c12):
    """Reference dedup + ranking for a few lanes (rows): key/e (n, 12) int64 in insertion order c = 0..11.
    -> (n, 4) winner candidate per new slot, (n,) number of real slots."""
    n = key.shape[0]
    k2 = np.sort(key * 16 + c12, axis=1)                  # by key, then insertion order
    cs = k2 & 15
    ks = k2 >> 4
    es = e[np.arange(n)[:, None], cs]
    gstart = np.ones((n, 12), dtype=bool)
    gstart[:, 1:] = ks[:, 1:] != ks[:, :-1]
    fs = np.flatnonzero(gstart)
    wv = np.minimum.reduceat((es * 16 + cs).reshape(-1), fs)      # per key: min (error, insertion)
    SK = np.full(n * 12, BIG, dtype=_I64)
    SK[fs] = (wv >> 4) * 16 + cs.reshape(-1)[fs]                  # rank: (error, first insertion of the key)
    WC = np.zeros(n * 12, dtype=_I64)
    WC[fs] = wv & 15
    SK = SK.reshape(n, 12)
    top = np.argsort(SK, axis=1)[:, :4]
    r = np.arange(n)[:, None]
    return WC.reshape(n, 12)[r, top], (SK[r, top] < EINV * 16).sum(axis=1)


def _beam4_lanes(XT, lens, P0, I0, stats=None):
    """== adpcm.encode_beam_py(width=4, cands=3) over ONE window per lane (the window starts from one state).
    Reference, per sample: every beam entry (in beam order) proposes the 3 reconstructions around its bisect
    position; nxt[(p, next_idx)] keeps the first candidate with the smallest error (a dict key keeps the position
    of its first insertion); the new beam = the 4 smallest errors, ties in insertion order; the result is beam[0].
    Here the 12 candidates of a lane are numbered c = 3 * slot + rank (= insertion order).
    Fast path: sort by (error, c), keep the first 4. That is exactly the reference result when the first 4 real
    candidates have distinct keys and the errors of the first 5 real candidates strictly increase: each of them
    then wins its key (every other candidate has a larger error, or the same error and a later insertion), no
    other key can reach the first four places (its best error is >= the 5th error > the 4th), and the
    first-insertion position the reference uses to order equal errors never matters. Lanes that fail the test
    (about 10% of the steps) take the full dedup (_beam4_exact_rows). Layout: slot-major (4 or 12 rows x lanes).
    Empty beam slots carry an error >= EINV, so they sort after every real candidate."""
    T, L = XT.shape
    P = np.zeros((4, L), dtype=_I64)
    I = np.zeros((4, L), dtype=_I64)
    E = np.full((4, L), EINV, dtype=_I64)
    P[0] = P0
    I[0] = I0
    E[0] = 0
    PAR = np.zeros((T, 4, L), dtype=np.uint8)
    NIB = np.zeros((T, 4, L), dtype=np.uint8)
    act = _active_counts(lens, T)
    COLS = np.arange(L)
    c12 = C12[:, 0]
    nslow = 0
    for t in range(T):
        A = act[t]
        if A == 0:
            break
        s = XT[t, :A]
        Pa, Ia, Ea = P[:, :A], I[:, :A], E[:, :A]
        cols = COLS[:A]
        base = Ia * 16
        g = np.searchsorted(SD_G, (s - Pa) + Ia * OFF)
        g -= base
        ix = (LO_TAB[g] + base)[:, None, :] + J3C                   # (4, 3, A) table rows of the 3 candidates
        tt = TAB[ix]
        p = _clamp((tt >> 12) + (Pa - (1 << 17))[:, None, :], -32768, 32767)
        e = p - s
        e *= e
        e += Ea[:, None, :]
        tt = tt.reshape(12, A)                                      # row c = 3 * slot + rank = insertion order
        p = p.reshape(12, A)
        e = e.reshape(12, A)
        srt = (e * 16 + C12).T.copy()                               # (A, 12): per lane (error, insertion)
        srt.sort(axis=1)
        top = srt[:, :5].T                                          # (5, A)
        cw = top[:4] & 15
        e5 = top >> 4
        p4 = p[cw, cols]
        t4 = tt[cw, cols]
        n4 = (t4 >> 4) & 127
        k4 = (p4 << 7) | n4
        real = e5 < EINV
        bad = ((k4[PI6] == k4[PJ6]) & real[PJ6]).any(axis=0)
        bad |= ((e5[1:] == e5[:-1]) & real[1:]).any(axis=0)
        e4 = e5[:4]
        if bad.any():
            rows = np.flatnonzero(bad)
            nslow += len(rows)
            ee = e[:, rows].T
            kk = np.where(ee < EINV, ((p[:, rows] << 7) | ((tt[:, rows] >> 4) & 127)).T, (1 << 40) + c12)
            cw_b, nr_b = _beam4_exact_rows(kk, ee, c12)
            cw_b = cw_b.T                                           # (4, n)
            cw[:, rows] = cw_b
            p4[:, rows] = p[cw_b, rows]
            t4[:, rows] = tt[cw_b, rows]
            n4[:, rows] = (t4[:, rows] >> 4) & 127
            eb = e[cw_b, rows]
            eb[np.arange(4)[:, None] >= nr_b[None, :]] = EINV
            e4[:, rows] = eb
        P[:, :A] = p4
        I[:, :A] = n4
        E[:, :A] = e4
        PAR[t, :, :A] = cw // 3
        NIB[t, :, :A] = t4 & 15
    if stats is not None:
        stats['lane_steps'] = stats.get('lane_steps', 0) + int(act.sum())
        stats['slow_steps'] = stats.get('slow_steps', 0) + nslow
    OUT = np.zeros((T, L), dtype=np.uint8)
    b = np.zeros(L, dtype=_I64)
    for t in range(T - 1, -1, -1):                                  # backtrack from beam[0]
        A = act[t]
        if A == 0:
            continue
        r = COLS[:A]
        OUT[t, :A] = NIB[t, b[:A], r]
        b[:A] = PAR[t, b[:A], r]
    return OUT, P[0].copy(), I[0].copy()


DIFF2T = np.ascontiguousarray(DIFFF.reshape(NSTEP, 16).T)       # (nibble, idx)
NEXT2T = np.ascontiguousarray(NEXTF.reshape(NSTEP, 16).T)
KBIG = 1 << 24                                                   # > any (p + 32768) * 89 + idx
NIB16 = np.arange(16, dtype=_I64)[:, None, None]


def _wide_lanes(XT, WT, lens, P0, I0, width=64):
    """== fix_music.beam_window (weighted beam over all 16 nibbles, `width` survivors) on independent lanes.
    The reference keeps its beam in the order np.argpartition returns, and that order decides ties (equal error
    through different parents, equal errors at the width boundary), which are frequent. So this keeps the SAME
    order: candidates are numbered like the reference (f = slot * 16 + nibble), each key's winner is the
    reference's np.lexsort((e, key)) choice (smallest error, then smallest f), the winners are listed in key order,
    and np.argpartition is called per lane on that identical float64 array. Everything else runs across lanes.
    Candidate arrays are (nibble, lane, slot) so the broadcast operands are outer axes; keep lanes per call small
    (temporaries under 512 KB). WT: the weights, time-major float64."""
    T, L = XT.shape
    P = np.zeros((L, width), dtype=_I64)
    I = np.zeros((L, width), dtype=_I64)
    E = np.full((L, width), np.inf)
    P[:, 0] = P0
    I[:, 0] = I0
    E[:, 0] = 0.0
    nb = np.ones(L, dtype=_I64)
    PAR = np.zeros((T, L, width), dtype=np.uint8)
    NIB = np.zeros((T, L, width), dtype=np.uint8)
    act = _active_counts(lens, T)
    slots = np.arange(width, dtype=_I64)
    lanes = np.arange(L, dtype=_I64)
    lncache = {}
    for t in range(T):
        A = act[t]
        if A == 0:
            break
        B = int(nb[:A].max())
        M = B * 16
        AB = A * B
        s = XT[t, :A]
        wt = WT[t, :A]
        Ia = I[:A, :B]
        p = _clamp(P[None, :A, :B] + DIFF2T[:, Ia], -32768, 32767)            # (16, A, B)
        e = (p - s[None, :, None]).astype(np.float64)
        e **= 2
        e *= wt[None, :, None]
        e += E[None, :A, :B]                                                  # == E[:, None] + wt * (p - s) ** 2
        ni = NEXT2T[:, Ia]
        key = (p + 32768) * 89 + ni
        f = NIB16 + 16 * slots[None, None, :B]                                # reference candidate number
        key = np.where(slots[None, None, :B] < nb[None, :A, None], key, KBIG)
        k2 = (key * 1024 + f).transpose(1, 0, 2).reshape(A, M)
        k2.sort(axis=1)
        fs = (k2 & 1023).ravel()
        ks = k2 >> 10
        ln = lncache.get((A, M))
        if ln is None:
            ln = lncache[(A, M)] = np.repeat(lanes[:A], M)
        fl = (fs & 15) * AB                                                   # flat index into (16, A, B)
        fl += ln * B
        fl += fs >> 4
        es = np.take(e.ravel(), fl)
        gstart = np.empty((A, M), dtype=bool)
        gstart[:, 0] = True
        np.not_equal(ks[:, 1:], ks[:, :-1], out=gstart[:, 1:])
        st = np.flatnonzero(gstart)
        gmin = np.minimum.reduceat(es, st)
        sizes = np.diff(np.append(st, A * M))
        pos = np.where(es == np.repeat(gmin, sizes), np.arange(A * M), A * M)
        wpos = np.minimum.reduceat(pos, st)                                   # first member with the minimal error
        keep = ks.ravel()[st] < KBIG
        glane = ln[st][keep]
        wf = fs[wpos][keep]
        we = es[wpos][keep]
        cnt = np.bincount(glane, minlength=A)
        off = np.zeros(A + 1, dtype=_I64)
        np.cumsum(cnt, out=off[1:])
        newF = np.zeros((A, width), dtype=_I64)
        small = cnt[glane] <= width
        newF[glane[small], (np.arange(len(glane)) - off[glane])[small]] = wf[small]
        for l in np.flatnonzero(cnt > width).tolist():
            a, b = off[l], off[l + 1]
            sel = np.argpartition(np.array(we[a:b]), width - 1)[:width]
            newF[l] = wf[a:b][sel]
        newnb = np.minimum(cnt, width)
        ok = slots[None, :] < newnb[:, None]
        n_, b_ = newF & 15, newF >> 4
        fl = n_ * AB + lanes[:A, None] * B + b_
        P[:A] = np.where(ok, np.take(p.ravel(), fl), 0)
        I[:A] = np.where(ok, np.take(ni.ravel(), fl), 0)
        E[:A] = np.where(ok, np.take(e.ravel(), fl), np.inf)
        PAR[t, :A] = b_
        NIB[t, :A] = n_
        nb[:A] = newnb
    b = np.argmin(E, axis=1)                                                  # first minimum, like the reference
    Pe, Ie = P[lanes, b], I[lanes, b]
    OUT = np.zeros((T, L), dtype=np.uint8)
    for t in range(T - 1, -1, -1):
        A = act[t]
        if A == 0:
            continue
        r = lanes[:A]
        OUT[t, :A] = NIB[t, r, b[:A]]
        b[:A] = PAR[t, r, b[:A]]
    return OUT, Pe, Ie


# ---------------------------------------------------------------- unit runners and the chain solver

LANE_CHUNK = {'greedy': 8192, 'beam4': 4096, 'wide': 48}            # per-step temporaries stay under 512 KB
KERNELS = {'greedy': _greedy_lanes, 'beam4': _beam4_lanes}


def run_lanes(kind, pays, starts):
    """Run independent units of one kind from the given start states. pays: list of payload tuples (samples[,
    weights]); starts: list of (pred, idx). -> list of (nibbles uint8 array, (pred, idx))."""
    n = len(pays)
    res = [None] * n
    if not n:
        return res
    order = sorted(range(n), key=lambda u: -len(pays[u][0]))
    ch = LANE_CHUNK[kind]
    for c0 in range(0, n, ch):
        grp = order[c0:c0 + ch]
        lens = np.array([len(pays[u][0]) for u in grp], dtype=_I64)
        T = int(lens[0])
        if T == 0:
            for u in grp:
                res[u] = (np.zeros(0, dtype=np.uint8), (int(starts[u][0]), int(starts[u][1])))
            continue
        XT = np.zeros((T, len(grp)), dtype=np.int32)
        for r, u in enumerate(grp):
            XT[:lens[r], r] = pays[u][0]
        P0 = np.array([starts[u][0] for u in grp], dtype=_I64)
        I0 = np.array([starts[u][1] for u in grp], dtype=_I64)
        if kind == 'wide':
            WT = np.zeros((T, len(grp)))
            for r, u in enumerate(grp):
                WT[:lens[r], r] = pays[u][1]
            OUT, Pe, Ie = _wide_lanes(XT, WT, lens, P0, I0)
        else:
            OUT, Pe, Ie = KERNELS[kind](XT, lens, P0, I0)
        OUT = OUT.T.copy()
        Pe, Ie = Pe.tolist(), Ie.tolist()
        for r, u in enumerate(grp):
            res[u] = (OUT[r, :lens[r]].copy(), (Pe[r], Ie[r]) if lens[r] else (int(starts[u][0]), int(starts[u][1])))
    return res


def guess_states(ws):
    """Plausible decoder states before each sample array (warm-up starts only; any value would be correct):
    (first sample, the step index nearest the mean |difference|)."""
    out = []
    for w in ws:
        w = np.asarray(w, dtype=_I64)
        if len(w) < 2:
            out.append((int(w[0]) if len(w) else 0, 0))
        else:
            out.append((int(w[0]), int(min(88, np.searchsorted(STEPS_NP, float(np.abs(np.diff(w)).mean()))))))
    return out


def solve_chains(chains, warm=256, deferred=('wide',), warm_kind=None, lockstep_min=128, target_lanes=16384,
                 stats=None):
    """Exact sequential encoding of chains of units, computed as vectorised lanes.

    chains: list of (start_state, units); unit = (kind, payload); payload = (samples[, weights]).
    A unit is a pure function of (payload, start state) -> (nibbles, end state) (run_lanes), and its start must be
    the end state of the unit before it in its chain, so a chain is inherently sequential.
    Each pass runs, for every chain, its FRONTIER unit (the first one not yet run from the end state of a
    consistent predecessor - its start is exact) plus up to D-1 units after it SPECULATIVELY, from the latest end
    state of their predecessor (or, if that has not run yet, the end state of a warm-up run over its last `warm`
    samples). With at least `lockstep_min` unfinished chains D = 1 (lockstep: no wasted runs, the chains alone
    fill the lanes); with fewer, D = target_lanes / chains (deep speculation: a few long chains). A unit is
    consistent when it was run from its predecessor's current end state; the frontier advances over consistent
    units, so when every frontier reached its chain's end, every unit was run from the true end state of its
    predecessor (induction from the chain heads) and the result is exactly the sequential one, whatever the
    guesses were. The encoders forget their start state within a few hundred samples, so most speculative
    results are already right. Units of a `deferred` kind (expensive, slow to forget their start) only run
    speculatively once their predecessor stopped changing.
    Returns per chain: (list of nibble arrays, end state)."""
    warm_kind = warm_kind or {'wide': 'beam4'}
    kinds, pays, prev, first, spans = [], [], [], [], []
    for start, units in chains:
        h = len(kinds)
        for j, (kind, pay) in enumerate(units):
            prev.append(len(kinds) - 1 if j else -1)
            first.append((int(start[0]), int(start[1])) if j == 0 else None)
            kinds.append(kind)
            pays.append(pay)
        spans.append((h, len(kinds), (int(start[0]), int(start[1]))))
    res, st = [None] * len(kinds), [None] * len(kinds)
    endguess = {}
    front = [h for h, _, _ in spans]
    changed_last = set()
    runs, passes, warms = {}, 0, 0

    def end_of(u):
        r = res[u]
        return r[1] if r is not None else endguess.get(u)

    def want(u):
        return first[u] if prev[u] < 0 else end_of(prev[u])

    while True:
        active = []
        for c, (h, e, _) in enumerate(spans):
            u = front[c]
            while u < e and res[u] is not None and st[u] == want(u):
                u += 1
            front[c] = u
            if u < e:
                active.append(c)
        if not active:
            break
        D = 1 if len(active) >= lockstep_min else max(1, -(-target_lanes // len(active)))
        wins = [(front[c], min(spans[c][1], front[c] + D)) for c in active]
        need = {}
        for a, b in wins:
            for u in range(a + 1, b):
                v = prev[u]
                if res[v] is None and v not in endguess:
                    x = pays[v][0]
                    need.setdefault(warm_kind.get(kinds[v], kinds[v]), []).append((v, x[max(0, len(x) - warm):]))
        for k, lst in need.items():
            g0 = guess_states([w for _, w in lst])
            if not warm:
                for (v, _), g in zip(lst, g0):
                    endguess[v] = g
                continue
            warms += len(lst)
            for (v, _), (_, end) in zip(lst, run_lanes(k, [(w,) for _, w in lst], g0)):
                endguess[v] = end
        fronts = set(front[c] for c in active)
        cand = [u for a, b in wins for u in range(a, b) if res[u] is None or st[u] != want(u)]
        cset = set(cand)
        now = [u for u in cand if not (kinds[u] in deferred and u not in fronts and
                                       (res[prev[u]] is None or prev[u] in cset or prev[u] in changed_last))]
        passes += 1
        starts = {u: want(u) for u in now}
        by_kind = {}
        for u in now:
            by_kind.setdefault(kinds[u], []).append(u)
        changed = set()
        for k, us in by_kind.items():
            runs[k] = runs.get(k, 0) + len(us)
            for u, r in zip(us, run_lanes(k, [pays[u] for u in us], [starts[u] for u in us])):
                if r[1] != end_of(u):
                    changed.add(u)
                res[u], st[u] = r, starts[u]
        changed_last = changed
    if stats is not None:
        stats['units'] = stats.get('units', 0) + len(kinds)
        for k, n in runs.items():
            stats['runs_' + k] = stats.get('runs_' + k, 0) + n
        stats['passes'] = stats.get('passes', 0) + passes
        stats['warmups'] = stats.get('warmups', 0) + warms
    return [([res[u][0] for u in range(h, e)], res[e - 1][1] if e > h else s0) for h, e, s0 in spans]


GREEDY_UNIT = 1024


def stream_units(kind, x, window=1024):
    """Cut one stream into units: beam4 = encode_beam's own windows (its beam restarts every `window` samples);
    greedy = arbitrary pieces (the greedy encoder has no windows; its only state is (pred, idx))."""
    w = window if kind == 'beam4' else GREEDY_UNIT
    return [(kind, (x[a:a + w],)) for a in range(0, len(x), w)]


def encode_streams(jobs, stats=None, window=1024):
    """jobs: list of (kind, samples, pred, idx); kind 'beam4' == adpcm.encode_beam_py(width=4, cands=3, window) or
    'greedy' == adpcm.encode_samples_py(search=True). All jobs are encoded together (lanes across jobs).
    -> list of (nibbles uint8 array, (pred, idx))."""
    chains = [((int(p), int(i)), stream_units(kind, np.asarray(x), window)) for kind, x, p, i in jobs]
    return [(np.concatenate(nl) if nl else np.zeros(0, dtype=np.uint8), end)
            for nl, end in solve_chains(chains, stats=stats)]
