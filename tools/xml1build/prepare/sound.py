"""xml1build.prepare.sound - prepare stage P4 `sound` (BUILDER_DESIGN.md 1.5; SPEC.md 27.6).

The XML1 Xbox ZSND banks (P1 xbox/sounds/zsds) as XML2 PC banks, in the layout the build reads as research
`sound/out` (Sources override):

  all_ima/eng/<c1>/<c2>/<bank>   every XML1 bank converted 1:1 (research/sound/convert_zsnd.py --batch
                                 --encoder auto --rekey character/=char/; the char/ aliases come from P2's
                                 names_xml1.json, passed explicitly) + _convert_report.json
  merged/eng/<c1>/<c2>/<bank>    every converted bank whose name XML2 also ships, merged into XML2's bank (XML2
                                 entries win; merge_zsnd.merge, the loop of the retired research/sound/merge_all.py)
                                 + _merge_report.json
  convert.log, merge.log         one line per bank (the research runs' stdout)

The 61 music banks (*_a / *_c) are converted too although P5 `music` replaces them in every build: the build plans
its sound banks from the all_ima file list (common.planned_sound_banks) and media checks each fixed music bank
against its 1:1 conversion (keys, entries, rates: media_music.structure_diff), so the 1:1 banks are the reference
the fixed ones are held to. With the compiled sound kernel they cost ~5 % of this stage's CPU time (and 371 MB of
cache); dropping them would need a planner that plans music banks from the disc instead (not worth the risk now).

Outputs are byte-identical to the research runs (tools/sound_equiv.py against build/_snd_final; the reports equal
after the roots are mapped and the timing / codec fields dropped). The audio codec is adpcm.codec(): the compiled
kernel when it is built and passes its self-check, else numpy; both give the same bytes.

Cache: <cache>/<disc_id>/prepared/sound-v<VERSION>-<key[:12]>/; key = VERSION + P1's key + the sha1 of P2's
names_xml1.json + the listing (rel, size, mtime) of XML2's Sounds/eng."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import (PrepareError, StageFailed, check_cancel, digest, find_ci, listing_digest, memory_budget_mb, ntfs_walk,
               pool_map, publish, read_stage, rebase_paths, rmtree, sha1_file, write_json_crlf)
from . import disc as P1, tables as P2
from ..lib import adpcm, convert_zsnd, merge_zsnd, zsnd     # were research/sound

STAGE = 'sound'
VERSION = 1
IMA, MERGED = 'all_ima/eng', 'merged/eng'       # below the stage directory = research/sound/out/<...>
ENCODER = 'auto'                                # greedy for stereo music, beam otherwise
REKEY = [('character/', 'char/')]               # XML1 character sounds also answer to XML2's char/ names
CONVERT_REPORT, MERGE_REPORT = '_convert_report.json', '_merge_report.json'


def _silent(*a, **k):
    """worker log (module level, picklable): the stage writes convert.log from the returned reports instead."""


def _convert_group(args):
    group, opts = args
    return convert_zsnd._group_job(group, opts)


def xml2_sounds(xml2) -> str:
    """XML2's Sounds/eng as a '/' path string (spelled as on disk)."""
    p = find_ci(xml2, 'Sounds', 'eng')
    if p is None:
        raise PrepareError('E_XML2_LANGUAGE', f'{xml2} has no Sounds/eng folder',
                           'the port needs an English X-Men Legends II install')
    return p.as_posix()


def iter_banks(root: str):
    """zsnd.iter_banks in NTFS order on any file system ('/' paths)."""
    for d, _, fs in ntfs_walk(root):
        for f in sorted(fs):
            if f.lower().endswith(('.zss', '.zsm')):
                yield f'{d}/{f}'


def group_cost_mb(args) -> float:
    """a worker's peak memory for one bank group (measured: ~0.5 GB of imports + ~12 MB per MB of Xbox data;
    manbst_v, 39 MB: 0.96 GB of commit)"""
    return 500 + 15 * sum(os.path.getsize(j[0]) for j in args[0]) / 2 ** 20


def convert_all(zsds: str, dst: str, names: dict, jobs: int, *, log=print, cancel=None, progress=None, rebase=None):
    """convert_zsnd.main --batch <zsds> <dst> --encoder auto --rekey character/=char/ with explicit names: the same
    jobs (biggest bank first), groups (convert_zsnd.group_jobs) and report. Returns the reports (sorted by out).
    rebase=(old, new): path prefix replaced in the report (the stage writes into a .partial directory)."""
    items = []
    for p in iter_banks(zsds):
        rel = os.path.relpath(p, zsds).replace(chr(92), '/')
        items.append((p, os.path.join(dst, rel), rel))
    items.sort(key=lambda j: -os.path.getsize(j[0]))  # biggest first for better parallel packing
    groups = convert_zsnd.group_jobs(items)
    opts = {'encoder': ENCODER, 'zsm_pcm': False, 'rekey': REKEY, 'verify': True, 'wav_dir': None, 'wav_max': 4,
            'names': names, 'log': _silent}
    os.makedirs(dst, exist_ok=True)
    res = pool_map(_convert_group, [(g, opts) for g in groups], jobs, cancel=cancel, progress=progress,
                   unit='bank groups', cost=group_cost_mb, budget=memory_budget_mb())
    reports = [r for rs in res for r in rs]
    reports.sort(key=lambda r: r['out'])
    reports = rebase_paths(reports, rebase)
    write_json_crlf(os.path.join(dst, CONVERT_REPORT), reports)
    return reports


def merge_all(conv: str, out: str, xml2_eng: str, *, log=print, cancel=None, rebase=None):
    """research/sound/merge_all.py as a function: every converted bank whose rel path XML2's Sounds/eng also has is
    merged into XML2's bank (XML2 entries win); empty XML1 banks are skipped. Writes _merge_report.json."""
    reps, lines = [], []
    for p in iter_banks(conv):
        check_cancel(cancel)
        rel = os.path.relpath(p, conv).replace(chr(92), '/')
        base = os.path.join(xml2_eng, rel)
        if not os.path.exists(base):
            continue
        add = zsnd.load(p)
        if not add.sounds:
            lines.append(f'skip (empty XML1 bank): {rel}')
            continue
        o = os.path.join(out, rel)
        os.makedirs(os.path.dirname(o), exist_ok=True)
        r = merge_zsnd.merge(base, p, o)
        reps.append(r)
        lines.append('%-20s base %4d + appended %4d sounds (%d dup keys skipped), tracks %d -> %s bytes' % (
            rel, r['base_sounds'], r['appended_sounds'], r['skipped_duplicate_keys'], r['out_tracks'],
            r['out_bytes']))
    os.makedirs(out, exist_ok=True)
    reps = rebase_paths(reps, rebase)
    write_json_crlf(os.path.join(out, MERGE_REPORT), reps)
    return reps, lines


# ============================================================================================== the stage
def stage_key(disc_stage: dict, tables_dir: Path, xml2_eng: str) -> str:
    return digest({'stage': STAGE, 'version': VERSION, 'disc': disc_stage.get('key'),
                   'names': sha1_file(Path(tables_dir) / P2.OUTPUTS['sound/names_xml1.json']),
                   'xml2_sounds': listing_digest(xml2_eng)})


def run(disc_dir, tables_dir, xml2, *, jobs=None, log=print, cancel=None, progress=None, force=False) -> dict:
    """P4 from a published P1 + P2 and the XML2 install; reuses the published output while its key matches.
    Returns {'dir', 'stage', 'cached'}; the build reads <dir> as research sound/out."""
    t0 = time.time()
    disc_dir, tables_dir = Path(disc_dir), Path(tables_dir)
    dst = read_stage(disc_dir)
    if not dst or dst.get('stage') != P1.STAGE:
        raise RuntimeError(f'{disc_dir} is not a published P1 disc directory')
    xml2_eng = xml2_sounds(xml2)
    key = stage_key(dst, tables_dir, xml2_eng)
    final = disc_dir.parent / 'prepared' / f'{STAGE}-v{VERSION}-{key[:12]}'
    st = read_stage(final)
    if st and st.get('key') == key and not force:
        log(f'[prepare] sound: cached ({final})')
        return {'dir': final, 'stage': st, 'cached': True}
    partial = final.with_name(final.name + '.partial')
    rmtree(partial)
    partial.mkdir(parents=True)
    jobs = max(1, int(jobs or os.cpu_count() or 1))
    zsds = (disc_dir / P1.XBOX / 'sounds' / 'zsds').as_posix()
    names = json.loads((tables_dir / P2.OUTPUTS['sound/names_xml1.json']).read_text(encoding='utf-8'))
    log(f'[prepare] sound: converting the XML1 banks ({jobs} jobs; sound codec: {adpcm.codec_status()})')
    t = time.time()
    rebase = (partial.as_posix(), final.as_posix())
    reports = convert_all(zsds, (partial / IMA).as_posix(), names, jobs, log=log, cancel=cancel, progress=progress,
                          rebase=rebase)
    t_convert = round(time.time() - t, 1)
    (partial / 'convert.log').write_text(''.join(json.dumps(r) + '\n' for r in reports), encoding='utf-8')
    bad = [r.get('in') for r in reports if not r.get('out_bytes')]
    if bad:
        raise StageFailed('E_PREPARE_SOUND', f'{len(bad)} bank(s) did not convert: {bad[:5]}', {'banks': bad})
    t = time.time()
    merged, lines = merge_all((partial / IMA).as_posix(), (partial / MERGED).as_posix(), xml2_eng, log=log,
                              cancel=cancel, rebase=rebase)
    t_merge = round(time.time() - t, 1)
    (partial / 'merge.log').write_text(''.join(x + '\n' for x in lines), encoding='utf-8')
    counts = {'banks': len(reports), 'aliases': sum(r.get('aliases', 0) for r in reports),
              'bytes': sum(r.get('out_bytes', 0) for r in reports), 'merged': len(merged),
              'codec': sorted({r.get('codec') for r in reports if r.get('codec')})}
    stage = {'stage': STAGE, 'version': VERSION, 'key': key, 'disc_key': dst.get('key'), 'xml2_sounds': xml2_eng,
             'jobs': jobs, 'counts': counts,
             'timings': {'convert': t_convert, 'merge': t_merge,
                         'convert_cpu': round(sum(r.get('seconds', 0) for r in reports), 1)},
             'seconds': round(time.time() - t0, 1)}
    stage = publish(partial, final, stage)
    log(f'[prepare] sound: done in {stage["seconds"]}s: {counts}; {stage["timings"]}')
    for old in final.parent.glob(f'{STAGE}-v*'):
        if old != final and not old.name.endswith('.partial'):
            rmtree(old)
    return {'dir': final, 'stage': stage, 'cached': False}
