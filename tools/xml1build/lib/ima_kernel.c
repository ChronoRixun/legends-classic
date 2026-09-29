/* ima_kernel.c - compiled IMA ADPCM codecs for research/sound (optional; loaded by adpcm_c.py through ctypes).

   Plain C99, no Python headers: every entry point takes plain arrays and returns 0 (or a negative error code).
   Build: python tools/build_sound_kernel.py (MSVC on Windows, cc elsewhere) -> build/native/ima_kernel-<platform>.*
   Each function reproduces a Python reference BIT FOR BIT (tools/xml1build/sound_selftest.py checks it):

     ima_greedy  == adpcm.encode_samples_py(search=True)  (nearest of the two reconstructions around the bisect
                    position, the lower one on a tie)
     ima_beam4   == adpcm.encode_beam_py(width=4, cands=3, window): the beam restarts every `window` samples from
                    the committed state; candidates in beam order x rank, a key (p, next index) keeps its first
                    insertion position and the first candidate with the smallest error, stable sort by error.
     ima_pc_decode / ima_xbox_decode == adpcm.pc_decode_py / adpcm.xbox_decode_py (see below)
     ima_wide    == tools/fix_music.beam_window (weighted beam over all 16 nibbles, `width` survivors). The reference
                    keeps its beam in np.argpartition order, which numpy leaves implementation-defined (it depends on
                    the numpy build and the CPU), so this kernel asks the caller for np.argpartition's answer through
                    a callback whenever that order can change the result - see ima_wide below.

   Arithmetic: the same integer operations as the references (errors of ima_beam4 in int64; the reference's are
   Python ints, which cannot differ for 16-bit audio), the same IEEE double operations in the same order in
   ima_wide (build without FMA contraction: /fp:precise, -ffp-contract=off). */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

/* the build passes -DKERNEL_SRC=<sha1 of this file with LF line ends>; adpcm_c.py refuses a library built from
   another version of the source */
#define STR2(x) #x
#define STR(x) STR2(x)
#ifdef KERNEL_SRC
#define KERNEL_SRC_SHA1 STR(KERNEL_SRC)
#else
#define KERNEL_SRC_SHA1 "unknown"
#endif
#define KERNEL_ABI "1"

#define E_ARG -1        /* bad argument (state out of range, width too large) */
#define E_MEM -2        /* out of memory */
#define E_CB -3         /* the argpartition callback failed (Python raised) */
#define E_SEL -4        /* the callback's selection broke an invariant (index out of range / not the smallest) */

static const int STEPS[89] = {7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55,
    60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544,
    598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660,
    4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500,
    20350, 22385, 24623, 27086, 29794, 32767};
static const int IDXT[16] = {-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8};

/* DIFF[i][n] = signed reconstruction delta, NEXT[i][n] = next step index (adpcm.DIFF / adpcm.NEXT);
   SD[i][r] / SN[i][r] = the deltas of row i sorted by (delta, nibble) and their nibbles (adpcm.SORTED_D / SORTED_N),
   SX[i][r] = NEXT[i][SN[i][r]] */
static int DIFF[89][16], NEXT[89][16], SD[89][16], SN[89][16], SX[89][16];
static volatile int inited;

static void init_tables(void)
{
    int i, n, a, b;
    if (inited)
        return;
    for (i = 0; i < 89; i++) {
        int s = STEPS[i], o[16];
        for (n = 0; n < 16; n++) {
            int d = s >> 3, ni = i + IDXT[n];
            if (n & 4) d += s;
            if (n & 2) d += s >> 1;
            if (n & 1) d += s >> 2;
            DIFF[i][n] = (n & 8) ? -d : d;
            NEXT[i][n] = ni < 0 ? 0 : ni > 88 ? 88 : ni;
            o[n] = n;
        }
        for (a = 1; a < 16; a++) {                  /* insertion sort by (delta, nibble) */
            int v = o[a];
            b = a - 1;
            while (b >= 0 && (DIFF[i][o[b]] > DIFF[i][v] || (DIFF[i][o[b]] == DIFF[i][v] && o[b] > v))) {
                o[b + 1] = o[b];
                b--;
            }
            o[b + 1] = v;
        }
        for (n = 0; n < 16; n++) {
            SD[i][n] = DIFF[i][o[n]];
            SN[i][n] = o[n];
            SX[i][n] = NEXT[i][o[n]];
        }
    }
    inited = 1;   /* every thread computes the same values; a second concurrent init is harmless */
}

static int bisect_left16(const int *a, int x)     /* == bisect.bisect_left(a[0:16], x); branch-free */
{
    int base = 0;
    base += a[base + 8] < x ? 8 : 0;
    base += a[base + 4] < x ? 4 : 0;
    base += a[base + 2] < x ? 2 : 0;
    base += a[base + 1] < x ? 1 : 0;
    return base + (a[base] < x);
}

static int clampp(int p) { return p > 32767 ? 32767 : p < -32768 ? -32768 : p; }

EXPORT const char *ima_kernel_info(void)
{
    return "ima_kernel abi=" KERNEL_ABI " src=" KERNEL_SRC_SHA1;
}

/* ---------------------------------------------------------------- greedy */

EXPORT int ima_greedy(const int32_t *x, int64_t n, int32_t pred, int32_t idx, uint8_t *out, int32_t *end)
{
    int64_t t;
    if (idx < 0 || idx > 88)
        return E_ARG;
    init_tables();
    for (t = 0; t < n; t++) {
        int s = x[t], row = idx, k = bisect_left16(SD[row], s - pred), j, best = -1, bn = 0, bp = 0;
        for (j = k - 1; j <= k; j++) {
            int p, e;
            if (j < 0 || j >= 16)
                continue;
            p = clampp(pred + SD[row][j]);
            e = p > s ? p - s : s - p;
            if (best < 0 || e < best) {
                best = e;
                bn = SN[row][j];
                bp = p;
            }
        }
        pred = bp;
        idx = NEXT[row][bn];
        out[t] = (uint8_t)bn;
    }
    end[0] = pred;
    end[1] = idx;
    return 0;
}

/* ---------------------------------------------------------------- beam 4 x 3 */

EXPORT int ima_beam4(const int32_t *x, int64_t n, int32_t pred, int32_t idx, int64_t window, uint8_t *out,
                     int32_t *end)
{
    uint8_t *par, *nib;
    int64_t pos;
    if (idx < 0 || idx > 88 || window < 1)
        return E_ARG;
    init_tables();
    if (window > n)
        window = n > 0 ? n : 1;
    par = (uint8_t *)malloc((size_t)window * 4);
    nib = (uint8_t *)malloc((size_t)window * 4);
    if (!par || !nib) {
        free(par);
        free(nib);
        return E_MEM;
    }
    for (pos = 0; pos < n; pos += window) {
        int len = (int)(n - pos < window ? n - pos : window), t, b, q;
        int64_t E[4] = {0, 0, 0, 0};
        int P[4], I[4], nb = 1;
        P[0] = pred;
        I[0] = idx;
        for (t = 0; t < len; t++) {
            int s = x[pos + t];
            int64_t ce[12], E2[4];
            int ck[12], cp[12], ci[12], cn[12], cb[12], nc = 0, ord[4], m = 0, P2[4], I2[4];
            for (b = 0; b < nb; b++) {              /* beam order x rank = the reference's dict insertion order */
                int row = I[b], lo = bisect_left16(SD[row], s - P[b]) - 1, j;
                lo = lo < 0 ? 0 : lo > 13 ? 13 : lo;
                for (j = lo; j < lo + 3; j++) {
                    int p = clampp(P[b] + SD[row][j]), ni = SX[row][j], key = (p + 32768) * 89 + ni, f = -1;
                    int64_t d = (int64_t)(p - s), e = E[b] + d * d;
                    for (q = 0; q < nc; q++)
                        if (ck[q] == key) {
                            f = q;
                            break;
                        }
                    if (f < 0) {
                        ck[nc] = key; ce[nc] = e; cp[nc] = p; ci[nc] = ni; cn[nc] = SN[row][j]; cb[nc] = b;
                        nc++;
                    } else if (e < ce[f]) {          /* the dict value is replaced, the key keeps its position */
                        ce[f] = e; cn[f] = SN[row][j]; cb[f] = b;
                    }
                }
            }
            for (q = 0; q < nc; q++) {              /* the first 4 of a stable sort by error */
                int64_t e = ce[q];
                int a;
                if (m == 4 && !(e < ce[ord[3]]))
                    continue;
                a = m < 4 ? m++ : 3;
                while (a > 0 && ce[ord[a - 1]] > e) {
                    ord[a] = ord[a - 1];
                    a--;
                }
                ord[a] = q;
            }
            for (q = 0; q < m; q++) {
                int c = ord[q];
                E2[q] = ce[c]; P2[q] = cp[c]; I2[q] = ci[c];
                par[t * 4 + q] = (uint8_t)cb[c];
                nib[t * 4 + q] = (uint8_t)cn[c];
            }
            for (q = 0; q < m; q++) {
                E[q] = E2[q]; P[q] = P2[q]; I[q] = I2[q];
            }
            nb = m;
        }
        b = 0;                                      /* commit the path of beam[0] */
        for (t = len - 1; t >= 0; t--) {
            out[pos + t] = nib[t * 4 + b];
            b = par[t * 4 + b];
        }
        pred = P[0];
        idx = I[0];
    }
    free(par);
    free(nib);
    end[0] = pred;
    end[1] = idx;
    return 0;
}

/* ---------------------------------------------------------------- decoders

   ima_pc_decode   == adpcm.pc_decode_py: headerless IMA from (0, 0), mono low nibble first, stereo L = low nibble;
                      out = int16 (channels, n) row-major.
   ima_xbox_decode == adpcm.xbox_decode_py: 36-byte blocks per channel, every block restarts from its header; out =
                      int16 (channels, blocks * 64); stats = blocks, bad_idx, reserved_nonzero, hdr_state_mismatch,
                      tail_bytes. */

EXPORT int ima_pc_decode(const uint8_t *data, int64_t nbytes, int32_t channels, int16_t *out)
{
    int64_t i;
    init_tables();
    if (channels == 1) {
        int pred = 0, idx = 0;
        for (i = 0; i < nbytes; i++) {
            int n = data[i] & 15;
            pred = clampp(pred + DIFF[idx][n]);
            idx = NEXT[idx][n];
            out[2 * i] = (int16_t)pred;
            n = data[i] >> 4;
            pred = clampp(pred + DIFF[idx][n]);
            idx = NEXT[idx][n];
            out[2 * i + 1] = (int16_t)pred;
        }
    } else if (channels == 2) {
        int pl = 0, il = 0, pr = 0, ir = 0;
        int16_t *L = out, *R = out + nbytes;
        for (i = 0; i < nbytes; i++) {
            int n = data[i] & 15;
            pl = clampp(pl + DIFF[il][n]);
            il = NEXT[il][n];
            L[i] = (int16_t)pl;
            n = data[i] >> 4;
            pr = clampp(pr + DIFF[ir][n]);
            ir = NEXT[ir][n];
            R[i] = (int16_t)pr;
        }
    } else {
        return E_ARG;
    }
    return 0;
}

EXPORT int ima_xbox_decode(const uint8_t *data, int64_t nbytes, int32_t channels, int16_t *out, int64_t *stats)
{
    int64_t bs = 36 * (int64_t)channels, nblk, blk;
    int pp[8], pi[8], c;
    if (channels < 1 || channels > 8)
        return E_ARG;
    init_tables();
    nblk = nbytes / bs;
    stats[0] = nblk;
    stats[1] = stats[2] = stats[3] = 0;
    stats[4] = nbytes % bs;
    for (blk = 0; blk < nblk; blk++) {
        const uint8_t *B = data + blk * bs, *body = B + 4 * channels;
        for (c = 0; c < channels; c++) {
            const uint8_t *h = B + 4 * c;
            int pred = (int16_t)(h[0] | (h[1] << 8)), idx = h[2], k = 0, w, j;
            int16_t *o = out + (int64_t)c * nblk * 64 + blk * 64;
            if (idx > 88) {
                stats[1]++;
                idx = 88;
            }
            if (h[3])
                stats[2]++;
            if (blk > 0 && (pp[c] != pred || pi[c] != idx))
                stats[3]++;
            o[0] = (int16_t)pred;
            for (w = 0; w < 8; w++) {               /* 4-byte words interleaved per channel, low nibble first */
                const uint8_t *word = body + (w * channels + c) * 4;
                for (j = 0; j < 8 && k < 63; j++, k++) {
                    int n = (j & 1) ? word[j >> 1] >> 4 : word[j >> 1] & 15;
                    pred = clampp(pred + DIFF[idx][n]);
                    idx = NEXT[idx][n];
                    o[k + 1] = (int16_t)pred;
                }
            }
            pp[c] = pred;
            pi[c] = idx;
        }
    }
    return 0;
}

/* ---------------------------------------------------------------- wide weighted beam (fix_music.beam_window)

   Reference, per sample s (weight wt), beam = list of states (p, idx, err) in slot order:
     every slot b and nibble n proposes candidate f = 16*b + n: p' = clamp(p + DIFF), idx' = NEXT,
     e = err + wt * (double)(p' - s)^2, key = (p' + 32768) * 89 + idx';
     order = np.lexsort((e, key)); the first candidate of every key (smallest e, then smallest f) is kept, in key
     order: cand (M entries); if M > width: cand = cand[np.argpartition(e[cand], width - 1)[:width]].
   At the end: b = np.argmin(err) (first minimum), backtrack.

   What argpartition's (implementation-defined) answer decides:
     (a) the SET of survivors, only if the width-th and (width+1)-th smallest errors are equal;
     (b) the ORDER of the survivors (their slot numbers). It matters only when, at the next sample, the smallest
         error of a key that survives is reached from two different slots (the smaller f wins; the winner's
         parent and nibble are what the backtracking follows), or, after the last sample, when the smallest
         error is held by two slots (argmin takes the first).
   Nothing else depends on it: a key's smallest error and its state (p', idx') are the same whoever wins, so the
   arrays passed to argpartition are the same whatever the earlier orders were, and a key that does not survive
   leaves no trace.

   Lazy mode (the default):
   - Only candidates with e <= T can matter, where T >= the (width+1)-th smallest key error: a slot's
     reconstructions rise monotonically with the rank (SD order), so its errors fall and then rise around the
     bisect position k, and T comes from a first pass over ranks k-1 and k of every slot (the (width+1)-th smallest
     error over the distinct keys seen there bounds the true one from above). The second pass walks each slot
     outward from k while e <= T and deduplicates those candidates in f order with a hash table.
   - Without a tie at the width boundary the survivors (the width smallest) are kept in a provisional order.
   - np.argpartition's answer is asked only when it is needed - at once for a boundary tie, for the previous
     sample when (b) happens (the beam is renumbered and the sample recomputed), for the last sample when the
     final minimum is tied - on the FULL candidate list of that sample, recomputed from the beam before it and
     sorted into key order.
   Eager mode (lazy = 0) expands everything and asks every time M > width; the self-test checks that both modes
   give the reference result. M <= width keeps the key order (no argpartition), as the reference does.

   cb(m): the caller runs np.argpartition(abuf[:m], width - 1)[:width] and stores it in sel[0..width-1];
   returns 1 on success. stats (optional, 4 x int64, accumulated): samples, samples with M > width,
   callback calls, recomputed samples. */

typedef int (*argpart_cb)(int64_t m);

#define WMAX 64
#define CMAX (WMAX * 16)
#define HBITS 11
#define HSIZE (1 << HBITS)

typedef struct {
    int32_t P[WMAX], I[WMAX];
    double E[WMAX];
    int nb;
} Beam;

typedef struct {                /* the deduplicated candidates ("winners") of one sample, in f order */
    int32_t p[CMAX], ni[CMAX], f[CMAX];
    uint32_t key[CMAX];
    double e[CMAX];
    uint8_t tie[CMAX];          /* the smallest error is reached from two slots */
    uint16_t ord[CMAX];         /* the winners in key order (valid when sorted) */
    int m, sorted, full;        /* full: every candidate was considered (argpartition's input is complete) */
} Cands;

typedef struct {
    uint32_t stamp[HSIZE], cur;
    uint16_t slot[HSIZE];
    uint64_t sa[CMAX], sb[CMAX];
    double tmp[CMAX];
    int32_t surv[WMAX];
    Cands c[2];
} WideCtx;

/* C->ord = the winners in key order (keys are distinct): LSD radix sort of (key - kmin) << 10 | index */
static void sort_cands(WideCtx *W, Cands *C)
{
    int m = C->m, j, shift;
    uint32_t kmin = 0xffffffffu, kmax = 0;
    uint64_t *src = W->sa, *dst = W->sb, *t;
    if (C->sorted)
        return;
    for (j = 0; j < m; j++) {
        if (C->key[j] < kmin) kmin = C->key[j];
        if (C->key[j] > kmax) kmax = C->key[j];
    }
    for (j = 0; j < m; j++)
        src[j] = ((uint64_t)(C->key[j] - kmin) << 10) | (uint64_t)j;
    for (shift = 10; shift < 34 && (shift == 10 || (((uint64_t)(kmax - kmin) << 10) >> shift)); shift += 8) {
        int cnt[256], i, tot = 0;
        memset(cnt, 0, sizeof cnt);
        for (i = 0; i < m; i++)
            cnt[(src[i] >> shift) & 255]++;
        if (m == 0 || cnt[(src[0] >> shift) & 255] == m)
            continue;
        for (i = 0; i < 256; i++) {
            int c = cnt[i];
            cnt[i] = tot;
            tot += c;
        }
        for (i = 0; i < m; i++)
            dst[cnt[(src[i] >> shift) & 255]++] = src[i];
        t = src;
        src = dst;
        dst = t;
    }
    for (j = 0; j < m; j++)
        C->ord[j] = (uint16_t)(src[j] & 1023);
    C->sorted = 1;
}

/* k-th smallest (0-based) of a[0..n-1] (reorders a); afterwards a[0..k-1] <= a[k] <= a[k+1..] */
static double select_kth(double *a, int n, int k)
{
    int lo = 0, hi = n - 1;
    while (hi > lo) {
        int i = lo, j = hi, mid = lo + ((hi - lo) >> 1);
        double x, t;
        if (a[mid] < a[lo]) { t = a[mid]; a[mid] = a[lo]; a[lo] = t; }
        if (a[hi] < a[lo]) { t = a[hi]; a[hi] = a[lo]; a[lo] = t; }
        if (a[hi] < a[mid]) { t = a[hi]; a[hi] = a[mid]; a[mid] = t; }
        x = a[mid];
        while (i <= j) {
            while (a[i] < x) i++;
            while (x < a[j]) j--;
            if (i <= j) {
                t = a[i]; a[i] = a[j]; a[j] = t;
                i++;
                j--;
            }
        }
        if (k <= j) hi = j;
        else if (k >= i) lo = i;
        else break;
    }
    return a[k];
}

static void hash_reset(WideCtx *W)
{
    if (++W->cur == 0) {
        memset(W->stamp, 0, sizeof W->stamp);
        W->cur = 1;
    }
}

/* add candidate f (in increasing f order) to C: a key's winner is its first candidate with the smallest error */
static void add_cand(WideCtx *W, Cands *C, int f, int p, int ni, double e)
{
    uint32_t key = (uint32_t)((p + 32768) * 89 + ni), h = (key * 2654435761u) >> (32 - HBITS);
    for (;;) {
        if (W->stamp[h] != W->cur) {
            int m = C->m++;
            W->stamp[h] = W->cur;
            W->slot[h] = (uint16_t)m;
            C->key[m] = key;
            C->p[m] = p;
            C->ni[m] = ni;
            C->e[m] = e;
            C->f[m] = f;
            C->tie[m] = 0;
            return;
        }
        if (C->key[W->slot[h]] == key) {
            int w = W->slot[h];
            if (e < C->e[w]) {
                C->e[w] = e;
                C->f[w] = f;
                C->tie[w] = 0;
            } else if (e == C->e[w] && (f >> 4) != (C->f[w] >> 4)) {
                C->tie[w] = 1;
            }
            return;
        }
        h = (h + 1) & (HSIZE - 1);
    }
}

static double cand_err(const Beam *B, int b, int p, int s, double wt)
{
    double d = (double)(p - s);
    return B->E[b] + wt * (d * d);
}

/* every candidate of the beam */
static void expand_full(WideCtx *W, const Beam *B, int s, double wt, Cands *C)
{
    int b, k;
    hash_reset(W);
    C->m = 0;
    for (b = 0; b < B->nb; b++) {
        const int *dr = DIFF[B->I[b]], *nr = NEXT[B->I[b]];
        for (k = 0; k < 16; k++) {
            int p = clampp(B->P[b] + dr[k]);
            add_cand(W, C, b * 16 + k, p, nr[k], cand_err(B, b, p, s, wt));
        }
    }
    C->sorted = 0;
    C->full = 1;
}

/* only the candidates with e <= T (see above); -> 0 when that does not apply (the caller expands everything): the
   first pass saw <= width distinct keys, the target is outside 16 bits (then clamping can break the monotonic
   order), or the weight is negative / NaN (the errors would not fall and rise) */
static int expand_pruned(WideCtx *W, const Beam *B, int s, double wt, int width, Cands *C)
{
    int b, m1 = 0, kp[WMAX];
    double T;
    if (B->nb * 2 <= width || s > 32767 || s < -32768 || !(wt >= 0.0))
        return 0;
    hash_reset(W);
    C->m = 0;
    for (b = 0; b < B->nb; b++) {             /* pass 1: ranks k-1, k (the two reconstructions around s) */
        const int *sd = SD[B->I[b]], *sx = SX[B->I[b]];
        int k = bisect_left16(sd, s - B->P[b]), r;
        kp[b] = k;
        for (r = k - 1; r <= k; r++) {
            if (r >= 0 && r < 16) {
                int p = clampp(B->P[b] + sd[r]);
                add_cand(W, C, 0, p, sx[r], cand_err(B, b, p, s, wt));   /* f unused: only the minimum counts */
            }
        }
    }
    m1 = C->m;
    if (m1 <= width)
        return 0;
    memcpy(W->tmp, C->e, sizeof(double) * m1);
    T = select_kth(W->tmp, m1, width);
    hash_reset(W);
    C->m = 0;
    for (b = 0; b < B->nb; b++) {             /* pass 2: ranks [a, z) around k with e <= T, added in nibble order */
        const int *sd = SD[B->I[b]], *sn = SN[B->I[b]], *sx = SX[B->I[b]];
        int k = kp[b], a, z, r, q = 0, pr[16], rk[16], i;
        double er[16];
        for (r = k - 1; r >= 0; r--) {
            int p = clampp(B->P[b] + sd[r]);
            double e = cand_err(B, b, p, s, wt);
            if (e > T) break;
            pr[r] = p;
            er[r] = e;
        }
        a = r + 1;
        for (r = k; r < 16; r++) {
            int p = clampp(B->P[b] + sd[r]);
            double e = cand_err(B, b, p, s, wt);
            if (e > T) break;
            pr[r] = p;
            er[r] = e;
        }
        z = r;
        for (r = a; r < z; r++) {             /* sort the ranks by nibble (f order) */
            int v = r, j = q - 1;
            while (j >= 0 && sn[rk[j]] > sn[v]) {
                rk[j + 1] = rk[j];
                j--;
            }
            rk[j + 1] = v;
            q++;
        }
        for (i = 0; i < q; i++) {
            r = rk[i];
            add_cand(W, C, b * 16 + sn[r], pr[r], sx[r], er[r]);
        }
    }
    C->sorted = 0;
    C->full = 0;
    return 1;
}

/* np.argpartition's survivors of C (a full candidate list) in its order -> W->surv (winner indices). The answer
   is checked: indices in range and distinct, and - for a sample kept provisionally - the same set (errors <= v). */
static int ask(WideCtx *W, Cands *C, int width, double *abuf, int64_t *sel, argpart_cb cb, int check, double v,
               int64_t *stats)
{
    int j;
    sort_cands(W, C);
    for (j = 0; j < C->m; j++)
        abuf[j] = C->e[C->ord[j]];
    if (stats) stats[2]++;
    if (cb((int64_t)C->m) != 1)
        return E_CB;
    for (j = 0; j < C->m; j++)
        W->tmp[j] = 0.0;
    for (j = 0; j < width; j++) {
        int64_t q = sel[j];
        if (q < 0 || q >= C->m || W->tmp[q] != 0.0)
            return E_SEL;
        W->tmp[q] = 1.0;
        W->surv[j] = C->ord[q];
        if (check && !(C->e[W->surv[j]] <= v))
            return E_SEL;
    }
    return 0;
}

static void set_beam(const Cands *C, const int32_t *surv, int nb, Beam *B, uint8_t *par, uint8_t *nib)
{
    int j;
    for (j = 0; j < nb; j++) {
        int c = surv[j];
        B->P[j] = C->p[c];
        B->I[j] = C->ni[c];
        B->E[j] = C->e[c];
        par[j] = (uint8_t)(C->f[c] >> 4);
        nib[j] = (uint8_t)(C->f[c] & 15);
    }
    B->nb = nb;
}

EXPORT int ima_wide(const int32_t *x, const double *w, int64_t n, int32_t pred, int32_t idx, int32_t width,
                    int32_t lazy, double *abuf, int64_t *sel, argpart_cb cb, uint8_t *out, int32_t *end,
                    int64_t *stats)
{
    WideCtx *W;
    uint8_t *PAR, *NIB;
    Beam B, Bp;                 /* the beam, and the beam before the previous sample (to recompute that sample) */
    int32_t surv[CMAX];
    double pv = 0.0, emin;
    int pknown = 1, rc = 0, cur = 0, j, b, ties;
    int64_t t;
    if (idx < 0 || idx > 88 || width < 1 || width > WMAX)
        return E_ARG;
    init_tables();
    W = (WideCtx *)malloc(sizeof(WideCtx));
    PAR = (uint8_t *)malloc((size_t)(n > 0 ? n : 1) * width);
    NIB = (uint8_t *)malloc((size_t)(n > 0 ? n : 1) * width);
    if (!W || !PAR || !NIB) {
        rc = E_MEM;
        goto done;
    }
    memset(W->stamp, 0, sizeof W->stamp);
    W->cur = 0;
    B.P[0] = pred;
    B.I[0] = idx;
    B.E[0] = 0.0;
    B.nb = 1;
    Bp = B;
    for (t = 0; t < n; t++) {
        Cands *C = &W->c[cur], *Pv = &W->c[cur ^ 1];
        int s = x[t], ns, known, part;
        double wt = w[t], v64 = 0.0;
        if (stats) stats[0]++;
        for (;;) {
            if (!(lazy && expand_pruned(W, &B, s, wt, width, C)))
                expand_full(W, &B, s, wt, C);
            part = !C->full || C->m > width;        /* a pruned list implies M > width */
            if (part) {
                int need = 1;
                if (lazy) {
                    double v65;
                    memcpy(W->tmp, C->e, sizeof(double) * C->m);
                    v65 = select_kth(W->tmp, C->m, width);
                    v64 = W->tmp[0];
                    for (j = 1; j < width; j++)
                        if (W->tmp[j] > v64) v64 = W->tmp[j];
                    need = v64 == v65;              /* a tie at the boundary: the set itself is argpartition's */
                }
                if (need) {
                    if (!C->full)
                        expand_full(W, &B, s, wt, C);
                    if ((rc = ask(W, C, width, abuf, sel, cb, 0, 0.0, stats)) != 0)
                        goto done;
                    memcpy(surv, W->surv, sizeof(int32_t) * width);
                    known = 1;
                } else {                            /* the width smallest, provisionally in f order */
                    int q = 0;
                    for (j = 0; j < C->m; j++)
                        if (C->e[j] <= v64) {
                            if (q == width) {
                                rc = E_SEL;
                                goto done;
                            }
                            surv[q++] = j;
                        }
                    if (q != width) {
                        rc = E_SEL;
                        goto done;
                    }
                    known = 0;
                }
                ns = width;
            } else {                                /* no selection: the reference keeps the key order */
                sort_cands(W, C);
                for (j = 0; j < C->m; j++)
                    surv[j] = C->ord[j];
                ns = C->m;
                known = 1;
            }
            if (!pknown) {                          /* does the previous sample's order decide a survivor here? */
                int tie = 0;
                for (j = 0; j < ns && !tie; j++)
                    tie = C->tie[surv[j]];
                if (tie) {
                    /* renumber the previous sample's survivors in np.argpartition's order, redo this sample */
                    expand_full(W, &Bp, x[t - 1], w[t - 1], Pv);
                    if ((rc = ask(W, Pv, width, abuf, sel, cb, 1, pv, stats)) != 0)
                        goto done;
                    set_beam(Pv, W->surv, width, &B, PAR + (t - 1) * width, NIB + (t - 1) * width);
                    pknown = 1;
                    if (stats) stats[3]++;
                    continue;
                }
            }
            break;
        }
        if (stats && part) stats[1]++;
        Bp = B;
        set_beam(C, surv, ns, &B, PAR + t * width, NIB + t * width);
        pknown = known;
        pv = v64;
        cur ^= 1;
    }
    /* argmin takes the first minimum: if two slots hold it, their order must be argpartition's */
    emin = B.E[0];
    ties = 0;
    for (j = 1; j < B.nb; j++) {
        if (B.E[j] < emin) {
            emin = B.E[j];
            ties = 0;
        } else if (B.E[j] == emin) {
            ties = 1;
        }
    }
    if (ties && !pknown) {
        Cands *L = &W->c[cur ^ 1];
        expand_full(W, &Bp, x[n - 1], w[n - 1], L);
        if ((rc = ask(W, L, width, abuf, sel, cb, 1, pv, stats)) != 0)
            goto done;
        set_beam(L, W->surv, width, &B, PAR + (n - 1) * width, NIB + (n - 1) * width);
    }
    b = 0;
    for (j = 1; j < B.nb; j++)
        if (B.E[j] < B.E[b]) b = j;
    end[0] = B.P[b];
    end[1] = B.I[b];
    for (t = n - 1; t >= 0; t--) {
        out[t] = NIB[t * width + b];
        b = PAR[t * width + b];
    }
done:
    free(W);
    free(PAR);
    free(NIB);
    return rc;
}
