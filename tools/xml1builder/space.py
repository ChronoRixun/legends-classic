"""xml1builder.space - free-space estimates (BUILDER_DESIGN.md 1.3; measured in phase 1b on Owen's PC).

The output: 4.43 GB with movies (the phase-1b prepared build was 4.82 GB including the 372 MB music snapshot that
builder mode leaves out), 3.35 GB without. The cache: P1 2.16 GB (1.5 GB without the movies) + P2-P5 1.05 GB.
need = (estimate - bytes already there) * 1.1 per volume; when the output and the cache share a volume, both needs
must fit together."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

OUT_BYTES = {True: 4_430_000_000, False: 3_350_000_000}          # movies on / off
CACHE_BYTES = {True: 3_210_000_000, False: 2_550_000_000}
MARGIN = 1.1


def folder_bytes(folder) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(folder):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def existing(path) -> Path:
    p = Path(path).resolve()
    while not p.exists() and p.parent != p:
        p = p.parent
    return p


def volume(path) -> str:
    p = existing(path)
    drive = os.path.splitdrive(str(p))[0]
    if drive:
        return drive.upper() + '\\'
    try:                                                   # POSIX: the mount point
        while not os.path.ismount(p) and p.parent != p:
            p = p.parent
    except OSError:
        pass
    return str(p)


def free_bytes(path) -> int:
    return shutil.disk_usage(existing(path)).free


def report(*, out=None, cache=None, disc_id=None, movies=True, out_present=None, cache_present=None,
           sizes=None) -> dict:
    """{out: {volume, need, free, ok}, cache: {...}} for the folders given (need in bytes, already reduced by what a
    previous build / cache holds). sizes: (output bytes, cache bytes) instead of the measured estimates."""
    out_bytes, cache_bytes = sizes or (OUT_BYTES[bool(movies)], CACHE_BYTES[bool(movies)])
    rep = {}
    if out:
        present = folder_bytes(out) if out_present is None and Path(out).exists() else (out_present or 0)
        need = max(0, int((out_bytes - present) * MARGIN))
        rep['out'] = {'volume': volume(out), 'need': need, 'free': free_bytes(out)}
        rep['out']['ok'] = rep['out']['free'] >= need
    if cache:
        if cache_present is None:
            d = Path(cache) / disc_id if disc_id else None
            cache_present = folder_bytes(d) if d is not None and d.exists() else 0
        need = max(0, int((cache_bytes - cache_present) * MARGIN))
        rep['cache'] = {'volume': volume(cache), 'need': need, 'free': free_bytes(cache)}
        rep['cache']['ok'] = rep['cache']['free'] >= need
        if 'out' in rep and rep['out']['volume'].lower() == rep['cache']['volume'].lower():
            both = rep['out']['need'] + need
            rep['out']['ok'] = rep['cache']['ok'] = rep['out']['free'] >= both
    return rep
