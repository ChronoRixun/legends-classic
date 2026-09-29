"""xml1build.prepare.music - prepare stage P5 `music` (BUILDER_DESIGN.md 1.5; SPEC.md 27.6).

XML1's 61 music banks (every *_a / *_c stream bank of P1's sounds/zsds whose samples are all stereo) rebuilt for
XMen2.exe's stream player by tools/fix_music.py (`fix` with its defaults: 44.1 kHz kept, beam encoder, cross-faded
seams; its docstring explains the layered 0x20 layout both engines use and why a 1:1 conversion plays wrong), in the
layout the build reads as research `sound/music0x20` (Sources override):

  banks/eng/<c1>/<c2>/<bank>.zss   + _fix_music_report.json   (= research/sound/music0x20/banks/eng)
  music.log                        one line per bank (fix_music's stdout)
  check.json                       media_music.check_bank of every bank against its Xbox original

Acceptance. Every bank is checked with media_music.check_bank in the worker that made it - the same engine
simulation the build's media module runs (XMen2.exe's stream split vs XML1's layers, correlation per voice and per
5 s window) - and the stage publishes nothing unless all 61 pass (StageFailed E_PREPARE_MUSIC). Byte identity with
another PC's banks is NOT the criterion: fix_music's wide beam keeps its survivors in np.argpartition order, and
numpy leaves the order of tied elements to its partition kernel, which depends on the numpy build and the CPU
(BUILDER_DESIGN.md 1.5, fact 2). On Owen's PC the banks are byte-identical to build/_snd_final/music/eng.

Nothing under research/ is read: the fallback music folders media once searched (banks_all, banks_22k,
_previous_attempt) resolve inside this stage's directory in prepared mode, where they do not exist.

Cache: <cache>/<disc_id>/prepared/music-v<VERSION>-<key[:12]>/; key = VERSION + P1's key + the listing of XML2's
Sounds/eng (the report's xml2_ships_same_name)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import (StageFailed, digest, listing_digest, memory_budget_mb, pool_map, publish, read_stage, rebase_paths,
               rmtree, write_json_crlf)
from . import disc as P1
from .sound import xml2_sounds
from .. import media_music as MM
from ..lib import adpcm, fix_music         # were research/sound/adpcm.py, tools/fix_music.py

STAGE = 'music'
VERSION = 1
BANKS = 'banks/eng'                       # below the stage directory = research/sound/music0x20/<...>
REPORT = '_fix_music_report.json'
OPTS = {'rate_mode': 'keep', 'body': 'beam', 'seam': 'xfade', 'flatten': None, 'force': False, 'wav_dir': None,
        'wav_seconds': None}              # fix_music.py fix defaults


def _silent(*a, **k):
    """worker log (module level, picklable): the stage writes music.log from the returned reports instead."""


def _music_job(job):
    """one bank: fix_music's own job wrapper (errors become report entries), then the engine check against the Xbox
    original. Returns (fix_music report, check result or None)."""
    rep = fix_music._job(job)
    if rep.get('error') or rep.get('skipped') or not rep.get('out'):
        return rep, None
    return rep, MM.check_job(rep['out'], job[0])


def bank_cost_mb(job) -> float:
    """a worker's peak memory for one music bank (fix_music + the check; measured: ~0.5 GB of imports + ~105 MB
    per MB of Xbox data: nuke_c, 21 MB, peaks at 2.7 GB of commit, sewer2_c at 1.6 GB)"""
    return 600 + 110 * os.path.getsize(job[0]) / 2 ** 20


def collect(zsds: str):
    """fix_music.collect([zsds], None): the stereo *_a / *_c banks (sorted paths)."""
    return fix_music.collect([zsds], None)


def stage_key(disc_stage: dict, xml2_eng: str) -> str:
    return digest({'stage': STAGE, 'version': VERSION, 'disc': disc_stage.get('key'),
                   'xml2_sounds': listing_digest(xml2_eng)})


def run(disc_dir, xml2, *, jobs=None, log=print, cancel=None, progress=None, force=False) -> dict:
    """P5 from a published P1 and the XML2 install; reuses the published output while its key matches.
    Returns {'dir', 'stage', 'cached'}; the build reads <dir> as research sound/music0x20."""
    t0 = time.time()
    disc_dir = Path(disc_dir)
    dst = read_stage(disc_dir)
    if not dst or dst.get('stage') != P1.STAGE:
        raise RuntimeError(f'{disc_dir} is not a published P1 disc directory')
    xml2_eng = xml2_sounds(xml2)
    key = stage_key(dst, xml2_eng)
    final = disc_dir.parent / 'prepared' / f'{STAGE}-v{VERSION}-{key[:12]}'
    st = read_stage(final)
    if st and st.get('key') == key and not force:
        log(f'[prepare] music: cached ({final})')
        return {'dir': final, 'stage': st, 'cached': True}
    partial = final.with_name(final.name + '.partial')
    rmtree(partial)
    partial.mkdir(parents=True)
    jobs = max(1, int(jobs or os.cpu_count() or 1))
    zsds = (disc_dir / P1.XBOX / 'sounds' / 'zsds').as_posix()
    out = (partial / BANKS).as_posix()
    opts = dict(OPTS, log=_silent, xbox_root=zsds, xml2_root=xml2_eng)
    banks = collect(zsds)
    work = [(p, os.path.join(out, *fix_music.rel3(p).split('/')).replace('\\', '/'), opts) for p in banks]
    work.sort(key=lambda j: -os.path.getsize(j[0]))          # biggest first for better packing (= fix_music.main)
    log(f'[prepare] music: {len(work)} music banks ({jobs} jobs; sound codec: {adpcm.codec_status()})')
    t = time.time()
    budget = memory_budget_mb()
    res = pool_map(_music_job, work, jobs, cancel=cancel, progress=progress, unit='banks', cost=bank_cost_mb,
                   budget=budget)
    t_fix = round(time.time() - t, 1)
    rebase = (partial.as_posix(), final.as_posix())
    reps = rebase_paths([r for r, _ in res], rebase)
    os.makedirs(out, exist_ok=True)
    write_json_crlf(os.path.join(out, REPORT), reps)
    checks = {}
    for (rep, chk), (src, dst_path, _) in zip(res, work):
        rel = fix_music.rel3(src)
        checks[rel] = rebase_paths(chk, rebase) if chk is not None else {'ok': False, 'problems': [
            rep.get('error') or rep.get('skipped') or 'no output']}
    write_json_crlf(partial / 'check.json', checks)
    (partial / 'music.log').write_text(''.join(json.dumps(
        {'out': r.get('out'), 'flags': [sr.get('flags_out') for sr in r.get('samples', [])],
         'rate': [sr.get('rate_out') for sr in r.get('samples', [])], 's': r.get('seconds_taken'),
         'error': r.get('error'), 'skipped': r.get('skipped')}) + '\n' for r in reps), encoding='utf-8')
    failed = {rel: c.get('problems') for rel, c in checks.items() if not c.get('ok')}
    if failed:
        raise StageFailed('E_PREPARE_MUSIC', f'{len(failed)} of {len(checks)} music banks failed '
                          f'(fix_music error or the engine check): {sorted(failed)[:5]}', {'failed': failed})
    counts = {'banks': len(reps), 'checked_ok': len(checks) - len(failed),
              'layered': sum(1 for r in reps for sr in r.get('samples', [])
                             if int(sr.get('flags_out', '0'), 16) & 0x20),
              'bytes': sum(r.get('bytes', 0) for r in reps),
              'codec': sorted({r.get('codec') for r in reps if r.get('codec')})}
    stage = {'stage': STAGE, 'version': VERSION, 'key': key, 'disc_key': dst.get('key'), 'xml2_sounds': xml2_eng,
             'jobs': jobs, 'memory_budget_mb': budget, 'counts': counts,
             'timings': {'fix': t_fix, 'fix_cpu': round(sum(r.get('seconds_taken', 0) for r in reps), 1)},
             'seconds': round(time.time() - t0, 1)}
    stage = publish(partial, final, stage)
    log(f'[prepare] music: done in {stage["seconds"]}s: {counts}; {stage["timings"]}')
    for old in final.parent.glob(f'{STAGE}-v*'):
        if old != final and not old.name.endswith('.partial'):
            rmtree(old)
    return {'dir': final, 'stage': stage, 'cached': False}
