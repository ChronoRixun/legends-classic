"""
Convert X-Men Legends (Xbox) ZSND banks ("ZSNDXBOX") to X-Men Legends II PC banks ("ZSNDPC  ").

    python convert_zsnd.py <in_bank> <out_bank> [options]
    python convert_zsnd.py --batch <xbox_zsds_root> <out_root> [--only nyc1,sewer1,...] [options]

options:
    --encoder E      beam (default) | greedy | classic | auto (greedy for stereo music, beam otherwise)
    --skip-existing  batch mode: keep outputs that already exist and parse (resume an interrupted batch)
    --zsm-pcm        store in-memory (.zsm) banks as 16-bit PCM (format 1) instead of IMA ADPCM: lossless vs the
                     Xbox decode, 4x file size. XMen2.exe 0x595137: format != 0x6a is memcpy'd into the
                     DirectSound buffer. NOT possible for .zss: the stream reader always decodes IMA (0x595aa0).
    --rekey old=new  alias every sound/track whose resolved name starts with <old> under <new> as well
                     (e.g. character/=char/ ); names come from names_xml1.json (resolve.py)
    --no-verify      skip decode/compare verification
    --wav DIR        also write decoded WAVs (first N files of each bank, see --wav-max)
    --jobs N         batch mode: convert N banks in parallel (multiprocessing; default: one per CPU)
    --only a,b       batch mode: only banks whose zone/base name is listed (e.g. nyc1,grso_m)
Empty XML1 banks (0 sounds, 100 bytes) are converted to empty PC banks (0x64-byte header).

Conversion rules (see zsnd.py for the formats):
  sounds  : 24-byte entries + hashes copied verbatim (identical layout on both platforms)
  samples : first 8 bytes (file index, flags, rate) copied, Xbox's 20 trailing zero bytes -> PC's 16
  files   : offset/size rebuilt, format := 0x6a (1 = raw PCM with --zsm-pcm), .xbadpcm -> .wav, hashes verbatim
  tracks  : 16-byte entries + ZTRK bytecode copied verbatim (bytecode references sound indices, which are kept;
            appended --rekey alias entries go after the originals so indices stay valid)
  audio   : Xbox ADPCM decoded (64 samples/block: header sample + nibbles 0..62, see adpcm.py) and re-encoded
            as one continuous headerless IMA ADPCM stream from state (0,0) with a beam-search encoder
            (a bit-exact nibble copy is impossible: every Xbox block restarts from an exact header sample).
            Sample rate and channel count are kept (XML1 music = 44100 Hz stereo; XML2 music is 22050 Hz).
  layout  : like XML2's own banks: file data in table order starting at header_size, each file 4-aligned,
            file_size exact.
"""
import os, sys, struct, json, time, array, math
from . import zsnd, adpcm, adpcm_np
from .zhash import elf_hash

PC_SAMPLE_TAIL = 16


def channels_of(bank, file_index):
    chs = set()
    for s in bank.samples:
        if s.u16(0) == file_index:
            chs.add(2 if s.raw[2] & 2 else 1)
    if len(chs) != 1:
        raise zsnd.ZsndError('file %d: ambiguous/unused channel count %s' % (file_index, chs))
    return chs.pop()


def default_names():
    """the developer-mode name table (research/sound/names_xml1.json under the repo root, xml1build.sources.REPO_ROOT);
    prepare stage P4 passes P2's regenerated table explicitly instead."""
    from ..sources import REPO_ROOT
    return os.path.join(str(REPO_ROOT), 'research', 'sound', 'names_xml1.json')


def load_names(path=None):
    try:
        return json.load(open(path or default_names()))
    except FileNotFoundError:
        return {}


def convert(in_path, out_path, encoder='beam', zsm_pcm=False, rekey=(), verify=True, wav_dir=None, wav_max=4,
            names=None, bank_rel=None, log=print):
    b = _prepare(in_path, out_path, encoder, zsm_pcm, bank_rel)
    enc = adpcm.codec().encode_streams(b['jobs']) if b['jobs'] else []
    return _finish(b, enc, rekey, verify, wav_dir, wav_max, names, log)


def convert_group(items, encoder='beam', zsm_pcm=False, rekey=(), verify=True, wav_dir=None, wav_max=4, names=None,
                  log=print):
    """convert() for several banks at once: items = [(in_path, out_path, bank_rel), ...] -> reports. Same outputs;
    the audio of all the banks is encoded in ONE encode_streams call of adpcm.codec() (with numpy, small banks share
    the lanes); a bank's 'seconds' = its own work + its share of the joint encoding, by samples."""
    bs = [_prepare(i, o, encoder, zsm_pcm, r) for i, o, r in items]
    alljobs = [j for b in bs for j in b['jobs']]
    t = time.time()
    enc = adpcm.codec().encode_streams(alljobs) if alljobs else []
    te = time.time() - t
    tot = sum(len(j[1]) for j in alljobs) or 1
    reps, k = [], 0
    for b in bs:
        n = len(b['jobs'])
        share = te * sum(len(j[1]) for j in b['jobs']) / tot
        reps.append(_finish(b, enc[k:k + n], rekey, verify, wav_dir, wav_max, names, log, extra=share))
        k += n
    return reps


def _prepare(in_path, out_path, encoder, zsm_pcm, bank_rel):
    """convert() part 1: parse the Xbox bank, decode its audio, list the IMA encoding jobs."""
    t0 = time.time()
    if bank_rel is None:
        bank_rel = '/'.join(in_path.replace(os.sep, '/').replace(chr(92), '/').split('/')[-3:])
    xb = zsnd.load(in_path)
    pcm = bool(zsm_pcm) and out_path.lower().endswith('.zsm')
    if xb.platform != 'xbox':
        raise zsnd.ZsndError('input is not an Xbox bank')
    report = {'in': in_path, 'out': out_path, 'encoder': 'pcm' if pcm else encoder, 'sounds': len(xb.sounds), 'samples': len(xb.samples),
              'files': len(xb.files), 'tracks': len(xb.tracks), 'blocks': 0, 'aliases': 0, 'codec': adpcm.codec_name()}
    # ---- audio: decode every file, then IMA-encode all files/channels of the bank together (adpcm.codec(): the
    # compiled kernel, or numpy lanes; identical to adpcm.xbox_to_pc file by file)
    files_out = []
    refs = {}
    jobs, packs = [], []
    for f in xb.files:
        ch = channels_of(xb, f.index)
        data = xb.file_bytes(f)
        if pcm:
            ref, st = adpcm.xbox_decode(data, ch)
            n = len(ref[0])
            a = array.array('h', bytes(2 * n * ch))
            for c in range(ch):
                a[c::ch] = ref[c]
            audio = a.tobytes()
            fmt = 1
        else:
            enc = encoder if encoder != 'auto' else ('greedy' if ch == 2 else 'beam')
            if enc in ('beam', 'greedy'):
                ref, st = adpcm.codec().xbox_decode_np(data, ch)
                packs.append((len(files_out), [len(jobs) + c for c in range(ch)]))
                jobs.extend(('beam4' if enc == 'beam' else 'greedy', ref[c], 0, 0) for c in range(ch))
                audio = None
            else:
                audio, st, ref = adpcm.xbox_to_pc(data, ch, encoder=enc)
            fmt = 0x6a
        report['blocks'] += st['blocks'] * ch
        report['pcm_samples'] = report.get('pcm_samples', 0) + len(ref[0]) * ch
        for k in ('bad_idx', 'reserved_nonzero', 'tail_bytes'):
            report[k] = report.get(k, 0) + st[k]
        refs[f.index] = (ref, ch)
        name = xb.file_name(f)
        if name.lower().endswith('.xbadpcm'):
            name = name[:-8] + '.wav'
        nm = name.encode('latin1')[:63]
        meta = struct.pack('<III', 0, 0, fmt) + nm + b'\0' * (64 - len(nm))
        files_out.append((f.hashes, meta, audio))
    return {'t0': t0, 'busy': time.time() - t0, 'xb': xb, 'pcm': pcm, 'report': report, 'files_out': files_out,
            'refs': refs, 'jobs': jobs, 'packs': packs, 'out_path': out_path, 'bank_rel': bank_rel}


def _finish(bk, enc_out, rekey, verify, wav_dir, wav_max, names, log, extra=None):
    """convert() part 2: pack the encoded audio, build + write the PC bank, verify it, log the report. extra=None:
    'seconds' = wall time since _prepare started; else _prepare's time + extra + this part's time."""
    t1 = time.time()
    xb, pcm, report, files_out, refs = bk['xb'], bk['pcm'], bk['report'], bk['files_out'], bk['refs']
    out_path, bank_rel = bk['out_path'], bk['bank_rel']
    for i, js in bk['packs']:
        h, meta, _ = files_out[i]
        files_out[i] = (h, meta, adpcm_np.pack_np([enc_out[j][0] for j in js]))
    # ---- sample entries
    samples_out = []
    for s in xb.samples:
        raw = s.raw[:8] + b'\0' * PC_SAMPLE_TAIL
        if pcm:
            pass  # flags: bit2 (8-bit) stays clear -> 16-bit PCM
        samples_out.append((s.hashes, raw))
    # ---- sounds (+ optional aliases for renamed prefixes)
    sounds_out = [(s.hashes, s.raw) for s in xb.sounds]
    tracks_out = [(t.hashes, t.raw, xb.ztrk[i]) for i, t in enumerate(xb.tracks)]
    if rekey:
        names = names if names is not None else load_names()
        bank_names = names.get(bank_rel or '', {})
        existing = set(h for hs, _ in sounds_out for h in hs) | set(h for hs, _, _ in tracks_out for h in hs)
        for hs, raw in list(sounds_out):
            n = bank_names.get('%08x' % hs[0])
            for old, new in rekey:
                if n and n.startswith(old):
                    nh = elf_hash_name(new + n[len(old):])
                    if nh not in existing:
                        sounds_out.append(([nh], raw))
                        existing.add(nh)
                        report['aliases'] += 1
        for hs, raw, blob in list(tracks_out):
            n = bank_names.get('%08x' % hs[0])
            for old, new in rekey:
                if n and n.startswith(old):
                    nh = elf_hash_name(new + n[len(old):])
                    if nh not in existing:
                        tracks_out.append(([nh], raw, blob))
                        existing.add(nh)
                        report['aliases'] += 1
    out = build_pc(sounds_out, samples_out, files_out, tracks_out)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, 'wb') as fh:
        fh.write(out)
    report['in_bytes'] = len(xb.data)
    report['out_bytes'] = len(out)
    # ---- verification
    if verify:
        pc = zsnd.load(out_path)  # strict parse: raises on any structural inconsistency
        assert pc.platform == 'pc'
        assert [s.hashes for s in pc.sounds][:len(xb.sounds)] == [s.hashes for s in xb.sounds]
        assert [s.raw for s in pc.sounds][:len(xb.sounds)] == [s.raw for s in xb.sounds]
        assert len(pc.samples) == len(xb.samples) and len(pc.files) == len(xb.files)
        for a, b in zip(pc.samples, xb.samples):
            assert a.hashes == b.hashes and a.raw[:8] == b.raw[:8]
        for i, t in enumerate(xb.tracks):
            assert pc.ztrk[i].rstrip(b'\0') == xb.ztrk[i].rstrip(b'\0')
        worst = None
        exact_n = tot_n = 0
        snrs = []
        for f in pc.files:
            ref, ch = refs[f.index]
            data = pc.file_bytes(f)
            if pcm:
                a = array.array('h', data)
                dec = [a[c::ch] for c in range(ch)]
            else:
                dec = adpcm.codec().pc_decode_np(data, ch)
            if len(dec[0]) != len(ref[0]):
                raise AssertionError('file %d: decoded %d samples, expected %d' % (f.index, len(dec[0]), len(ref[0])))
            cmp = adpcm.compare(ref, dec)
            assert f.u32(8) == (1 if pcm else 0x6a)
            snrs.append(cmp['snr_db'])
            exact_n += cmp['exact_pct'] * cmp['n'] * ch
            tot_n += cmp['n'] * ch
            if worst is None or cmp['snr_db'] < worst[1]['snr_db']:
                worst = (pc.file_name(f), cmp)
            if wav_dir and f.index < wav_max:
                os.makedirs(wav_dir, exist_ok=True)
                rate = next(s.u32(4) for s in pc.samples if s.u16(0) == f.index)
                base = os.path.splitext(os.path.basename(out_path))[0] + '__' + pc.file_name(f).rsplit('.', 1)[0]
                adpcm.write_wav(os.path.join(wav_dir, base + '__pc.wav'), [adpcm._to_h(adpcm_np.np.asarray(c)) for c in dec], rate)
                adpcm.write_wav(os.path.join(wav_dir, base + '__xbox_ref.wav'), [adpcm._to_h(adpcm_np.np.asarray(c)) for c in ref], rate)
        report['verify_exact_pct'] = round(exact_n / tot_n, 3) if tot_n else None
        report['verify_worst_file'] = worst
        fin = sorted(x for x in snrs if x != float('inf'))
        report['verify_snr_db_median'] = fin[len(fin) // 2] if fin else 'inf'
    report['seconds'] = round(time.time() - bk['t0'] if extra is None else bk['busy'] + extra + time.time() - t1, 1)
    log(json.dumps(report), flush=True)
    return report


def elf_hash_name(n):
    return elf_hash(n.replace('\\', '/').lower())


def build_pc(sounds, samples, files, tracks):
    """Serialise a PC bank (same layout rules as XML2's shipped banks)."""
    es = zsnd.ESIZE[zsnd.MAGIC_PC]
    tabs = [sounds, samples, [(h, m) for h, m, _ in files], [], [(h, r) for h, r, _ in tracks], [], []]
    pos = 0x64
    layout = []
    for ti, t in enumerate(tabs):
        for hs, _ in t:
            assert len(hs) == 1, 'one key per entry expected'
        n = len(t)
        ko = pos
        pos += 8 * n
        vo = pos
        pos += es[ti] * n
        layout.append((n, ko, vo))
    ztrk_offs = []
    for _, _, blob in tracks:
        ztrk_offs.append(pos)
        pos += len(blob)
    header_size = (pos + 3) & ~3
    file_offs = []
    p = header_size
    for _, _, audio in files:
        p = (p + 3) & ~3
        file_offs.append((p, len(audio)))
        p += len(audio)
    total = p
    out = bytearray(total)
    out[0:8] = zsnd.MAGIC_PC
    struct.pack_into('<II', out, 8, total, header_size)
    for ti, (n, ko, vo) in enumerate(layout):
        struct.pack_into('<III', out, 0x10 + 12 * ti, n, ko, vo)
        keys = sorted((hs[0], idx) for idx, (hs, _) in enumerate(tabs[ti]))
        for k, (hh, idx) in enumerate(keys):
            struct.pack_into('<II', out, ko + 8 * k, hh, idx)
        for idx, (hs, raw) in enumerate(tabs[ti]):
            raw = bytearray(raw)
            if ti == 2:
                struct.pack_into('<II', raw, 0, *file_offs[idx])
            elif ti == 4:
                struct.pack_into('<I', raw, 8, ztrk_offs[idx])
            assert len(raw) == es[ti], (ti, len(raw))
            out[vo + es[ti] * idx: vo + es[ti] * (idx + 1)] = raw
    for (_, _, blob), o in zip(tracks, ztrk_offs):
        out[o:o + len(blob)] = blob
    for (_, _, audio), (o, n) in zip(files, file_offs):
        out[o:o + n] = audio
    return bytes(out)


def main(argv):
    opts = {'encoder': 'beam', 'zsm_pcm': False, 'rekey': [], 'verify': True, 'wav_dir': None, 'wav_max': 4}
    only = None
    njobs = os.cpu_count() or 1
    args = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--encoder': i += 1; opts['encoder'] = argv[i]
        elif a == '--zsm-pcm': opts['zsm_pcm'] = True
        elif a == '--no-verify': opts['verify'] = False
        elif a == '--rekey': i += 1; o, n = argv[i].split('='); opts['rekey'].append((o, n))
        elif a == '--wav': i += 1; opts['wav_dir'] = argv[i]
        elif a == '--wav-max': i += 1; opts['wav_max'] = int(argv[i])
        elif a == '--only': i += 1; only = set(argv[i].split(','))
        elif a == '--jobs': i += 1; njobs = int(argv[i])
        elif a == '--skip-existing': opts['skip_existing'] = True
        else: args.append(a)
        i += 1
    print('sound codec:', adpcm.codec_status(), flush=True)
    if args and args[0] == '--batch':
        src, dst = args[1], args[2]
        jobs = []
        for p in zsnd.iter_banks(src):
            rel = os.path.relpath(p, src).replace(chr(92), '/')
            base = os.path.basename(p).rsplit('.', 1)[0]
            zone = base.rsplit('_', 1)[0]
            if only and zone not in only and base not in only:
                continue
            jobs.append((p, os.path.join(dst, rel), rel))
        jobs.sort(key=lambda j: -os.path.getsize(j[0]))  # biggest first for better parallel packing
        groups = group_jobs(jobs)
        if njobs > 1:
            import multiprocessing as mp
            with mp.Pool(njobs) as pool:
                # chunksize 1: the default chunking handed the 4 biggest banks to one worker in a row
                reports = [r for rs in pool.starmap(_group_job, [(g, opts) for g in groups], chunksize=1) for r in rs]
        else:
            reports = [r for g in groups for r in _group_job(g, opts)]
        reports.sort(key=lambda r: r['out'])
        json.dump(reports, open(os.path.join(dst, '_convert_report.json'), 'w'), indent=1)
    else:
        opts.pop('skip_existing', None)
        convert(args[0], args[1], **opts)


GROUP_BYTES = 24 << 20     # worker job limits: Xbox data per group, and
GROUP_CHAINS = 512         # encoder chains (files x channels) per group; a bank with LANES_ALONE chains goes alone
LANES_ALONE = 256


def bank_chains(path):
    try:
        b = zsnd.load(path)
        return sum(channels_of(b, f.index) for f in b.files)
    except Exception:          # let the bank fail in its own worker job, as convert() reports it
        return LANES_ALONE


def group_jobs(jobs):
    """Split the (biggest-first) bank jobs into worker jobs. The numpy encoder needs many independent streams
    (files x channels) to fill its lanes without speculating (adpcm_np.solve_chains), so banks with fewer than
    LANES_ALONE streams are converted together, up to GROUP_CHAINS streams or GROUP_BYTES of Xbox data per job."""
    groups, cur, size, chains = [], [], 0, 0
    for j in jobs:
        n, c = os.path.getsize(j[0]), bank_chains(j[0])
        if n >= GROUP_BYTES or c >= LANES_ALONE:
            groups.append([j])
            continue
        cur.append(j)
        size += n
        chains += c
        if size >= GROUP_BYTES or chains >= GROUP_CHAINS:
            groups.append(cur)
            cur, size, chains = [], 0, 0
    if cur:
        groups.append(cur)
    return groups


def _group_job(group, opts):
    if opts.get('skip_existing') or len(group) == 1:
        return [_job(j, opts) for j in group]
    o = dict(opts)
    o.pop('skip_existing', None)
    return convert_group([(src, out, rel) for src, out, rel in group], **o)


def _job(job, opts):
    src, out, rel = job
    if opts.get('skip_existing') and os.path.exists(out):
        try:
            a, b = zsnd.load(src), zsnd.load(out)
            if b.platform == 'pc' and len(a.files) == len(b.files) and len(a.tracks) <= len(b.tracks):
                print(json.dumps({'in': src, 'out': out, 'skipped_existing': True}), flush=True)
                return {'in': src, 'out': out, 'skipped_existing': True}
        except Exception:
            pass
    o = dict(opts)
    o.pop('skip_existing', None)
    return convert(src, out, bank_rel=rel, **o)


if __name__ == '__main__':
    main(sys.argv[1:])
