"""
The optional compiled codec kernel (ima_kernel.c next to this file, loaded with ctypes) behind the same entry points
as adpcm_np: encode_streams, solve_chains, run_lanes, xbox_decode_np, pc_decode_np. Same results, bit for bit
(tools/xml1build/sound_selftest.py).

adpcm.codec() returns this module when load() succeeds, else adpcm_np; adpcm.codec_status() says which one and why.
load() succeeds when
  - XML1_SOUND_KERNEL is not 'off' / '0' / 'numpy' (a path in it names the library to load instead of the default),
  - the library exists: build/native/ima_kernel-<platform>.<dll|so|dylib> under the repo root
    (python tools/build_sound_kernel.py) or next to this file (the frozen builder ships it there, with ima_kernel.c),
  - it was built from this ima_kernel.c (the source sha1 compiled into it; checked when the .c file is present),
  - and a self-check on a synthetic signal gives the same results as adpcm_np and the pure-Python references
    (decoders, greedy, beam 4x3, the wide beam - lazy and eager).
Otherwise the numpy path is used, unchanged.

The kernel runs every stream sequentially (no speculation). The wide beam of fix_music asks numpy for
np.argpartition's answer through a callback whenever that answer can change the result (ima_kernel.c, ima_wide):
the argpartition order is numpy's own, so this path reproduces the numpy one on the same numpy build + CPU.
"""
import ctypes
import hashlib
import os
import sys
import sysconfig
import threading

import numpy as np

from ..sources import REPO_ROOT

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = str(REPO_ROOT)     # the repo (or, frozen, the bundle: $XML1_PORT_ROOT); was research/sound/.. /..
SOURCE = os.path.join(HERE, 'ima_kernel.c')
ENV = 'XML1_SOUND_KERNEL'
LIMIT = 1 << 20          # samples / predictors beyond +-2^20 go to the numpy path (int32 + no int64 overflow)
STATUS = 'not loaded'
_K = None
_TRIED = False
_LOCK = threading.Lock()
_CB = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int64)
_ERR = {-1: 'bad argument', -2: 'out of memory', -3: 'argpartition callback failed',
        -4: 'argpartition answer broke an invariant'}


def platform_tag():
    """e.g. win_amd64, win32, linux_x86_64: the tag in the library file name (one library per Python platform)."""
    return sysconfig.get_platform().replace('-', '_').replace('.', '_')


def lib_name():
    ext = '.dll' if os.name == 'nt' else '.dylib' if sys.platform == 'darwin' else '.so'
    return 'ima_kernel-' + platform_tag() + ext


def default_dir():
    return os.path.join(ROOT, 'build', 'native')


def source_sha1(path=None):
    """sha1 of the C source with LF line ends (the same on a CRLF checkout)."""
    with open(path or SOURCE, 'rb') as fh:
        return hashlib.sha1(fh.read().replace(b'\r\n', b'\n')).hexdigest()


def candidates():
    env = os.environ.get(ENV, '').strip()
    if env:
        return [env]
    return [os.path.join(default_dir(), lib_name()), os.path.join(HERE, lib_name())]


def disabled():
    return os.environ.get(ENV, '').strip().lower() in ('off', '0', 'no', 'numpy', 'false')


def load():
    """Load + self-check the kernel once per process. -> True if the kernel is in use (STATUS says why not)."""
    global _K, _TRIED, STATUS
    with _LOCK:
        if _TRIED:
            return _K is not None
        _TRIED = True
        if disabled():
            STATUS = f'numpy (kernel disabled by {ENV})'
            return False
        paths = [p for p in candidates() if os.path.isfile(p)]
        if not paths:
            STATUS = (f'numpy (no compiled kernel at {candidates()[0]}; build it with '
                      'python tools/build_sound_kernel.py)')
            return False
        path = paths[0]
        try:
            k = ctypes.CDLL(os.path.abspath(path))
            _declare(k)
            info = k.ima_kernel_info().decode('ascii', 'replace')
        except (OSError, AttributeError) as e:
            STATUS = f'numpy (cannot load {path}: {e})'
            return False
        if os.path.isfile(SOURCE):
            want = source_sha1()
            if ('src=' + want) not in info:
                STATUS = (f'numpy (stale kernel {path}: built from another ima_kernel.c ({info}); rebuild with '
                          'python tools/build_sound_kernel.py)')
                return False
        _K = k
        try:
            bad = self_check()
        except Exception as e:  # noqa: BLE001 - any failure means: do not use the kernel
            bad = f'{type(e).__name__}: {e}'
        if bad:
            _K = None
            STATUS = f'numpy (kernel {path} failed its self-check: {bad})'
            return False
        STATUS = f'compiled kernel {os.path.relpath(path, ROOT) if _under(path, ROOT) else path} ({info})'
        return True


def _under(p, root):
    try:
        return os.path.commonpath([os.path.abspath(p), root]) == root
    except ValueError:
        return False


def _declare(k):
    vp, i64, i32 = ctypes.c_void_p, ctypes.c_int64, ctypes.c_int32
    k.ima_kernel_info.restype = ctypes.c_char_p
    k.ima_kernel_info.argtypes = []
    k.ima_greedy.restype = ctypes.c_int
    k.ima_greedy.argtypes = [vp, i64, i32, i32, vp, vp]
    k.ima_beam4.restype = ctypes.c_int
    k.ima_beam4.argtypes = [vp, i64, i32, i32, i64, vp, vp]
    k.ima_wide.restype = ctypes.c_int
    k.ima_wide.argtypes = [vp, vp, i64, i32, i32, i32, i32, vp, vp, _CB, vp, vp, vp]
    k.ima_pc_decode.restype = ctypes.c_int
    k.ima_pc_decode.argtypes = [vp, i64, i32, vp]
    k.ima_xbox_decode.restype = ctypes.c_int
    k.ima_xbox_decode.argtypes = [vp, i64, i32, vp, vp]


# ---------------------------------------------------------------- single-stream calls

def fits(x, pred=0, idx=0):
    """Inputs the kernel takes: int samples and predictor within +-2^20, step index 0..88 (the numpy path takes
    anything; it gets the rest)."""
    if not (0 <= int(idx) <= 88 and -LIMIT <= int(pred) <= LIMIT):
        return False
    if len(x) == 0:
        return True
    a = np.asarray(x)
    if a.dtype.kind not in 'iu':
        return False
    return -LIMIT <= int(a.min()) and int(a.max()) <= LIMIT


def _i32(x):
    return np.ascontiguousarray(x, dtype=np.int32)


def _check(rc, what):
    if rc:
        raise RuntimeError(f'ima_kernel {what}: {_ERR.get(rc, rc)}')


def greedy(x, pred, idx):
    """== adpcm.encode_samples_py(x, pred, idx, out, search=True) -> (nibbles uint8, (pred, idx))."""
    x = _i32(x)
    out = np.empty(len(x), dtype=np.uint8)
    end = np.zeros(2, dtype=np.int32)
    _check(_K.ima_greedy(x.ctypes.data, len(x), int(pred), int(idx), out.ctypes.data, end.ctypes.data), 'greedy')
    return out, (int(end[0]), int(end[1]))


def beam4(x, pred, idx, window=1024):
    """== adpcm.encode_beam_py(x, pred, idx, width=4, cands=3, window) -> (nibbles uint8, (pred, idx))."""
    x = _i32(x)
    out = np.empty(len(x), dtype=np.uint8)
    end = np.zeros(2, dtype=np.int32)
    _check(_K.ima_beam4(x.ctypes.data, len(x), int(pred), int(idx), int(window), out.ctypes.data, end.ctypes.data),
           'beam4')
    return out, (int(end[0]), int(end[1]))


class _Wide:
    """Per-thread buffers + the argpartition callback of ima_wide."""

    def __init__(self, width):
        self.width = width
        self.abuf = np.zeros(width * 16, dtype=np.float64)
        self.sel = np.zeros(width, dtype=np.int64)
        self.stats = np.zeros(4, dtype=np.int64)
        abuf, sel, kth = self.abuf, self.sel, width - 1

        def cb(m):
            try:
                # a fresh float64 array like the reference's e[cand]; numpy's own argpartition decides
                sel[:] = np.argpartition(np.array(abuf[:m]), kth)[:width]
                return 1
            except BaseException:  # noqa: BLE001 - never let an exception cross the C frame
                return 0
        self.cb = _CB(cb)


_TLS = threading.local()


def _wide_ctx(width):
    d = getattr(_TLS, 'wide', None)
    if d is None:
        d = _TLS.wide = {}
    c = d.get(width)
    if c is None:
        c = d[width] = _Wide(width)
    return c


def wide(x, weights, pred, idx, width=64, lazy=True, stats=None):
    """== fix_music.beam_window(x, weights, pred, idx, width) -> (nibbles uint8, (pred, idx)). stats (dict): adds
    wide_samples, wide_partitions, wide_argpartition_calls, wide_recomputed."""
    x = _i32(x)
    w = np.ascontiguousarray(weights, dtype=np.float64)
    assert len(w) >= len(x)
    c = _wide_ctx(width)
    c.stats[:] = 0
    out = np.empty(len(x), dtype=np.uint8)
    end = np.zeros(2, dtype=np.int32)
    _check(_K.ima_wide(x.ctypes.data, w.ctypes.data, len(x), int(pred), int(idx), int(width), 1 if lazy else 0,
                       c.abuf.ctypes.data, c.sel.ctypes.data, c.cb, out.ctypes.data, end.ctypes.data,
                       c.stats.ctypes.data), 'wide')
    if stats is not None:
        for k, v in zip(('wide_samples', 'wide_partitions', 'wide_argpartition_calls', 'wide_recomputed'),
                        c.stats.tolist()):
            stats[k] = stats.get(k, 0) + v
    return out, (int(end[0]), int(end[1]))


# ---------------------------------------------------------------- adpcm_np-compatible entry points

def _u8(data):
    try:
        return np.frombuffer(data, dtype=np.uint8)
    except (TypeError, ValueError, BufferError):
        return np.frombuffer(bytes(data), dtype=np.uint8)


def xbox_decode_np(data, channels):
    """== adpcm_np.xbox_decode_np == adpcm.xbox_decode_py: (int16 array (channels, n), stats)."""
    if not 1 <= channels <= 8:
        from . import adpcm_np
        return adpcm_np.xbox_decode_np(data, channels)
    b = _u8(data)
    bs = 36 * channels
    nblk = len(b) // bs
    stats = {'blocks': nblk, 'bad_idx': 0, 'reserved_nonzero': 0, 'hdr_state_mismatch': 0, 'tail_bytes': len(b) % bs}
    if nblk == 0:
        return np.zeros((channels, 0), dtype=np.int16), stats
    out = np.empty((channels, nblk * 64), dtype=np.int16)
    st = np.zeros(5, dtype=np.int64)
    _check(_K.ima_xbox_decode(b.ctypes.data, len(b), channels, out.ctypes.data, st.ctypes.data), 'xbox_decode')
    stats['bad_idx'], stats['reserved_nonzero'], stats['hdr_state_mismatch'] = (int(v) for v in st[1:4])
    return out, stats


def pc_decode_np(data, channels):
    """== adpcm_np.pc_decode_np == adpcm.pc_decode_py, as an int16 array (channels, n)."""
    if channels not in (1, 2):
        from . import adpcm_np
        return adpcm_np.pc_decode_np(data, channels)
    b = _u8(data)
    out = np.empty((channels, len(b) * (2 if channels == 1 else 1)), dtype=np.int16)
    _check(_K.ima_pc_decode(b.ctypes.data, len(b), channels, out.ctypes.data), 'pc_decode')
    return out


def _unit_fits(kind, pay, start):
    return kind in ('greedy', 'beam4', 'wide') and fits(pay[0], *start)


def run_unit(kind, pay, start, stats=None):
    """One adpcm_np unit (kind, payload) from `start`: 'greedy' / 'beam4' (ONE beam window, however long) / 'wide'."""
    p, i = start
    if kind == 'greedy':
        return greedy(pay[0], p, i)
    if kind == 'beam4':
        return beam4(pay[0], p, i, max(1, len(pay[0])))
    if kind == 'wide':
        return wide(pay[0], pay[1], p, i, stats=stats)
    raise ValueError(kind)


def run_lanes(kind, pays, starts):
    """== adpcm_np.run_lanes: independent units -> list of (nibbles uint8 array, (pred, idx))."""
    if not all(_unit_fits(kind, pay, s) for pay, s in zip(pays, starts)):
        from . import adpcm_np
        return adpcm_np.run_lanes(kind, pays, starts)
    return [run_unit(kind, pay, (int(s[0]), int(s[1]))) for pay, s in zip(pays, starts)]


def solve_chains(chains, stats=None, **_):
    """== adpcm_np.solve_chains: per chain (start, units) -> (list of nibble arrays, end state), computed
    sequentially. Runs of units that one kernel call reproduces are merged: greedy units always; beam4 units (each
    one beam window) when every unit of the run but the last has the same length W and the last <= W (then one
    ima_beam4 call with window W restarts its beam exactly at the unit starts - adpcm_np.stream_units' cutting)."""
    if not all(_unit_fits(k, pay, (0, 0)) for _, units in chains for k, pay in units):
        from . import adpcm_np
        return adpcm_np.solve_chains(chains, stats=stats)
    res = []
    for start, units in chains:
        state = (int(start[0]), int(start[1]))
        if not fits((), *state):
            from . import adpcm_np
            return adpcm_np.solve_chains(chains, stats=stats)
        outs = []
        j = 0
        while j < len(units):
            kind, pay = units[j]
            if kind == 'wide':
                nl, state = wide(pay[0], pay[1], state[0], state[1], stats=stats)
                outs.append(nl)
                j += 1
                continue
            W = len(pay[0])
            e = j + 1
            while e < len(units) and units[e][0] == kind and (kind == 'greedy' or (
                    len(units[e - 1][1][0]) == W and len(units[e][1][0]) <= W and W > 0)):
                e += 1
            lens = [len(units[u][1][0]) for u in range(j, e)]
            x = units[j][1][0] if e == j + 1 else np.concatenate([np.asarray(units[u][1][0]) for u in range(j, e)])
            if kind == 'greedy':
                nl, state = greedy(x, state[0], state[1])
            else:
                nl, state = beam4(x, state[0], state[1], max(1, W))
            a = 0
            for n in lens:
                outs.append(nl[a:a + n])
                a += n
            j = e
        res.append((outs, state))
    if stats is not None:
        stats['units'] = stats.get('units', 0) + sum(len(u) for _, u in chains)
    return res


def encode_streams(jobs, stats=None, window=1024):
    """== adpcm_np.encode_streams: jobs = [(kind, samples, pred, idx)], kind 'beam4' (== encode_beam_py(width=4,
    cands=3, window)) or 'greedy' -> list of (nibbles uint8 array, (pred, idx))."""
    if not all(k in ('greedy', 'beam4') and fits(x, p, i) for k, x, p, i in jobs):
        from . import adpcm_np
        return adpcm_np.encode_streams(jobs, stats=stats, window=window)
    return [greedy(x, p, i) if k == 'greedy' else beam4(x, p, i, window) for k, x, p, i in jobs]


# ---------------------------------------------------------------- self-check

def _signal(n, seed):
    """Deterministic test audio: tones + noise bursts + full-scale clipping (ties from clamping) + silence."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    x = 9000 * np.sin(t * 0.031) + 4000 * np.sin(t * 0.173 + 1.0) + rng.normal(0, 600, n)
    x[n // 5: n // 5 + 300] *= 6                       # clipping
    x[n // 2: n // 2 + 200] = 0                        # silence
    x[3 * n // 4: 3 * n // 4 + 150] = rng.integers(-32768, 32768, 150)
    return np.clip(np.round(x), -32768, 32767).astype(np.int64)


def self_check():
    """Kernel vs adpcm_np and the pure-Python references on a synthetic signal. -> '' or what differed."""
    from . import adpcm
    from . import adpcm_np
    rng = np.random.default_rng(2)
    for ch, nb in ((1, 36 * 40 + 5), (2, 72 * 25), (2, 71), (1, 0)):
        raw = bytearray(rng.integers(0, 256, nb, dtype=np.uint8).tobytes())
        for blk in range(0, len(raw) - 36 * ch + 1, 36 * ch * 3):     # a few legal headers, the rest bad indices
            raw[blk + 2] = int(rng.integers(0, 89))
        raw = bytes(raw)
        a, sa = xbox_decode_np(raw, ch)
        r, sr = adpcm_np.xbox_decode_np(raw, ch)
        if not (np.array_equal(a, r) and a.dtype == r.dtype and sa == sr):
            return f'xbox_decode ({ch} ch, {nb} bytes)'
        ref = adpcm.pc_decode_py(raw, ch)
        got = pc_decode_np(raw, ch)
        if not (np.array_equal(got, adpcm_np.pc_decode_np(raw, ch)) and
                all(np.array_equal(np.frombuffer(q, np.int16), c) for q, c in zip(ref, got))):
            return f'pc_decode ({ch} ch, {nb} bytes)'
    x = _signal(5000, 1)
    for p, i in ((0, 0), (-1234, 57), (32767, 88)):
        a = greedy(x, p, i)
        ref = []
        e = adpcm.encode_samples_py(x.tolist(), p, i, ref, True)
        if a[0].tolist() != ref or a[1] != tuple(e):
            return f'greedy from {(p, i)}'
        a = beam4(x[:2600], p, i, 1024)
        rn, re_ = adpcm.encode_beam_py(x[:2600].tolist(), p, i, width=4, cands=3, window=1024)
        if a[0].tolist() != rn or a[1] != tuple(re_):
            return f'beam4 from {(p, i)}'
    (nl, end), = adpcm_np.encode_streams([('beam4', x, 5, 9)])
    b = beam4(x, 5, 9)
    if not (np.array_equal(nl, b[0]) and tuple(end) == b[1]):
        return 'beam4 vs adpcm_np'
    # wide beam windows (fix_music's weights 4 / 1 / 0.25), lazy and eager, against the numpy lanes
    wts = np.where(np.arange(len(x)) % 400 < 100, 4.0, np.where(np.arange(len(x)) % 400 < 300, 1.0, 0.25))
    wins = [(a, a + ln) for a, ln in ((0, 160), (700, 112), (1000, 97), (len(x) // 5, 180),
                                      (len(x) // 2 - 40, 120), (3 * len(x) // 4 - 20, 150), (4200, 1), (4300, 0))]
    starts = [(0, 0), (123, 30), (-900, 44), (5000, 70), (0, 0), (-32768, 88), (7, 7), (3, 4)]
    pays = [(x[a:e], wts[a:e]) for a, e in wins]
    ref = adpcm_np.run_lanes('wide', pays, starts)
    st = {}
    for lazy in (True, False):
        for (xa, wa), s, (rn, re_) in zip(pays, starts, ref):
            nl, end = wide(xa, wa, s[0], s[1], lazy=lazy, stats=st)
            if not (np.array_equal(nl, rn) and end == tuple(re_)):
                return f'wide ({"lazy" if lazy else "eager"}) from {s}'
    if not st.get('wide_recomputed') or not st.get('wide_argpartition_calls'):
        return f'wide: the test windows did not exercise the argpartition callback ({st})'
    return ''
