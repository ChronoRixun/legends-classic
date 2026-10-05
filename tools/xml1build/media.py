"""xml1build.media - XML1 sound banks, movies and movie subtitles (tools/xml1build/SPEC.md section 5.4).

Owns Sounds/eng/** (the XML1 and merged ZSND banks of ctx.planned_sound_banks()) and Movies/** (XML1 .sfd files
and subtitle XMLB/engb). Every file goes through ctx.copy_file / ctx.write_xmlb; nothing outside <out> is written.

Sounds
  * installs exactly the banks of ctx.planned_sound_banks(): 197 'x1' banks (research/sound/out/all_ima/eng) and
    18 'merged' banks (research/sound/out/merged/eng; they replace XML2's x_common, x_voice, menu_a/c, the hero
    and the colliding NPC banks, XML2 entries winning inside them). 'base' banks stay XML2's.
  * MUSIC. The 59 XML1 music banks (<zone>_a/_c.zss, all stereo) are installed from the fixed-layout banks of
    tools/fix_music.py (research/sound/music0x20/banks/eng, then .../banks_all/eng and .../banks_22k/eng;
    $XML1BUILD_MUSIC_DIR, a ';'-separated list, overrides) instead of all_ima, unless XML1BUILD_MUSIC=ima. Reason (media_music.py docstring): XML1
    interleaves the two layers of a combat bank (flag 0x20) in 32768-frame chunks, XMen2.exe splits the stream
    into 8192-frame chunks (0x595d60), so a 1:1 transcode feeds alternating slices of both layers to both voices,
    and 12 of the 29 layered all_ima banks even end inside layer 0 (XMen2.exe computes a non-positive voice
    length at EOF). A fixed bank must keep the plan bank's keys/entries (rate 1:1 or 2:1, 0x20 kept or cleared
    by --flatten) and every installed music bank is checked against the ORIGINAL Xbox bank by
    media_music.check_bank (engine voice i must be XML1 layer i; cached in <out>/_build/media_cache). A fixed
    bank that is missing or fails falls back to the plan's bank; that is an error when the plan's bank fails
    the check too (every layered bank), a note otherwise. Fixed banks are snapshotted into
    <out>/_build/media_cache/music_fixed and installed from there (registry source; builder mode, C.builder_mode:
    installed from the prepare cache's P5 directory, no snapshot); the pure provider
    bank_source(ctx, rel) names the research file behind any installed bank.
  * checks on every installed bank (strict zsnd parse of the bytes in <out>): ZSNDPC magic, exact file_size, IMA
    0x6a only, no stereo (0x02) / 8-bit (0x04) / unknown flag in a .zsm (the .zsm loader builds WAVEFORMATEX with
    nBlockAlign=2, 0x5950c3), rates fit the u16 the stream reader keeps (0x595acc), every layered stream ends
    after a complete layer-0 chunk (0x595d60), every ZTRK parses with sound refs in range, the path follows the
    two-letter rule of 0x592b00, bytes equal the source, 'music/<bank>' resolves in every XML1 music bank
    (0x477690), merged banks keep every XML2 entry (key, index, entry bytes, audio) of the bank they replace, an
    'x1' bank never replaces an XML2 bank, and no two banks share their first 9 characters (0x5913c4).

Movies (skipped with --no-movies)
  * the 34 XML1 NTSC movies xml1_xbox/movies/ntsc/<c1>/<c2>/<name>.sfd are copied byte for byte (the extra C1
    AIX/ADX stream stays) to Movies/ntsc/eng/<c1>/<c2>/<new>.sfd, new = movie_name(ctx, name). XMen2.exe
    0x57d15d-0x57d1e0 builds 'movies/ntsc/' + language + '/' + name + '.sfd' and 0x592b00(path, 2) inserts the
    first two characters of the name as sub directories. Sofdec structure (MPEG-1 pack, SofdecStream, E0 video
    geometry / frame rate, C0 ADX header) is compared with XML2's own movies; the copy is verified in full.
  * movie_name: 'x' + name while XML2 already ships a movie (or subtitle file) of that name: i101-i105, i107.
    Those six are referenced only by XML1's front-end menus/intro_*.py (not installed) and data/review_paths.eng
    (not ported); run() cross-checks every installed script anyway.

Subtitles (also with --no-movies)
  * xml1_assets/movies/<name>.eng -> Movies/<movie_name(name)>.XMLB + .engb (XMen2.exe 'movies/%s.xmlb',
    0x6a1448 via 0x5c9edb; same <SubTitles><item time life text/> schema as XML2's cine01). English text in both
    files, as for every other localized XML1 file.
  * overlapping items: XML1 gives most items life=9 while the next line starts 2-3 s later (XML1 replaced the
    line). An item's life is clamped to the start of the next item, so the lines show one at a time and in sync
    whether XML2 replaces, stacks or queues subtitles (XML2's own items abut, cine03, or leave gaps).
"""
from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from . import common as C
from . import media_music as MM

from .lib import merge_zsnd, zhash, zsnd, ztrk     # noqa: E402  were research/sound

MODULE = 'media'
X1_MOVIE_DIR = ('movies', 'ntsc')          # xml1_xbox/movies/ntsc/<c1>/<c2>/<name>.sfd (Xbox layout)
OUT_MOVIE_DIR = 'Movies/ntsc/eng'          # XML2 PC layout, English
# fixed-layout music banks (tools/fix_music.py), searched per bank in this order under research/: fix_music.py's
# default --out, a full-batch directory, the 22.05 kHz variant; every candidate is verified against the Xbox
# original and the first that passes wins. $XML1BUILD_MUSIC_DIR (';'-separated) replaces the list.
# The last entry is the previous complete 22.05 kHz batch (61 banks, all pass the Xbox-original check): it keeps the
# default build green while fix_music.py regenerates banks/eng; a bank there is used only when no newer candidate
# passes, and every candidate is checked the same way.
FIXED_MUSIC_DIRS = ('sound/music0x20/banks/eng', 'sound/music0x20/banks_all/eng', 'sound/music0x20/banks_22k/eng',
                    'sound/music0x20/_previous_attempt/banks/eng')
IMA_DIR = 'sound/out/all_ima/eng'
MERGED_DIR = 'sound/out/merged/eng'
MUSIC_ENV = 'XML1BUILD_MUSIC'              # fixed (default) | ima
MUSIC_DIR_ENV = 'XML1BUILD_MUSIC_DIR'      # directories of fixed music banks (<c1>/<c2>/<bank>.zss), ';'-separated
STAGE_DIR = 'media_cache/music_fixed'      # under <out>/_build: snapshot of the fixed banks that are installed
DEEP_ENV = 'XML1BUILD_MEDIA_DEEP'          # 1 (default) | 0: skip the decode-based music check
_MODE_WORDS = {'fixed': ('', 'fixed', 'fix', 'music0x20', '22050'),
               'ima': ('ima', 'all_ima', 'plan', 'raw', '44100', 'keep', 'off', '0', 'no', 'false')}
CLAMP_SUBTITLE_OVERLAPS = True
KNOWN_SAMPLE_FLAGS = MM.FLAG_LOOP | MM.FLAG_STEREO | MM.FLAG_LAYERED
BANK_NAME_CHECK = 9                        # already-loaded check compares 9 chars of the basename (0x5913c4)
ZONE_SUFFIXES = 'macvd'                    # soundfile -> <soundfile>_{m,a,c,v,d} (0x59228d)

_lock = threading.RLock()
_base_movie_cache = {}
_duration_cache = {}
_movies_index_cache = {}
SOFDEC_LIMIT = 2 * 1024 * 1024             # _sofdec_info parses the first 2 MB of a movie


# ============================================================================================ providers (pure)
def _base_movie_names(ctx):
    """stems of every movie-namespace file XML2 ships: Movies/**/<name>.sfd and Movies/<name>.{xmlb,engb}."""
    key = str(ctx.base)
    with _lock:
        if key not in _base_movie_cache:
            names = set()
            for k in ctx.base_index.keys():
                if not k.startswith('movies/'):
                    continue
                stem, ext = C.split_ext(k)
                if ext in ('.sfd', '.xmlb', '.engb'):
                    names.add(stem.rsplit('/', 1)[-1])
            _base_movie_cache[key] = frozenset(names)
        return _base_movie_cache[key]


def movie_name(ctx, x1_name) -> str:
    """XML2 name of an XML1 movie (pure; SPEC.md 5.0 provider). Lowercase stem; 'x' is prefixed while XML2
    already has a movie or subtitle file of that name (i101 -> xi101, ...). Accepts 'R106', 'i101.sfd',
    'movies/ntsc/i/1/i101.sfd'."""
    n = C.norm(x1_name).rsplit('/', 1)[-1]
    if n.endswith('.sfd'):
        n = n[:-4]
    taken = _base_movie_names(ctx)
    new = n
    while new in taken:
        new = 'x' + new
    return new


def movie_rel(name: str) -> str:
    """Movies/ntsc/eng/<c1>/<c2>/<name>.sfd for an XML2 movie name (0x592b00 two-letter sub directories)."""
    n = name.lower()
    return f'{OUT_MOVIE_DIR}/{n[0]}/{n[1]}/{n}.sfd'


def _music_mode_raw(ctx):
    v = ctx.opt('music', None)
    if v in (None, ''):
        v = os.environ.get(MUSIC_ENV, '')
    return str(v).strip().lower()


def music_mode(ctx) -> str:
    """'fixed' (default: XML1 music banks from the fixed-layout directories, see fixed_music_dirs) or 'ima'
    (the plan's all_ima 1:1 banks; A/B only)."""
    return 'ima' if _music_mode_raw(ctx) in _MODE_WORDS['ima'] else 'fixed'


def _prepared(ctx) -> bool:
    return getattr(getattr(ctx, 'sources', None), 'mode', None) == 'prepared'


def fixed_music_dirs(ctx):
    """[Path]: where fixed-layout music banks are looked for, in order: $XML1BUILD_MUSIC_DIR / args.music_dir
    (';'-separated; absolute, or relative to research/), else FIXED_MUSIC_DIRS under research/:
    sound/music0x20/banks/eng (fix_music.py's default --out), .../banks_all/eng, .../banks_22k/eng.
    Prepared mode (SPEC 27.6): only prepare stage P5's banks (the override of sound/music0x20/banks/eng) - no
    fallback folder and no $XML1BUILD_MUSIC_DIR, so a bank P5 lacks is an error, never a research/ file."""
    if _prepared(ctx):
        return [ctx.research_path(FIXED_MUSIC_DIRS[0])]
    v = ctx.opt('music_dir', None) or os.environ.get(MUSIC_DIR_ENV, '')
    if v:
        out = []
        for part in str(v).split(';'):
            if part.strip():
                q = Path(part.strip())
                out.append(q if q.is_absolute() else ctx.research_path(q))
        return out
    return [ctx.research_path(d) for d in FIXED_MUSIC_DIRS]


def _sub_of(rel):
    """'sounds/eng/n/y/nyc1_c.zss' -> 'n/y/nyc1_c.zss' (or None)."""
    n = C.norm(rel)
    return n[len('sounds/eng/'):] if n.startswith('sounds/eng/') else None


def fixed_music_candidates(ctx, rel):
    """existing <dir>/<c1>/<c2>/<bank>.zss files for a planned music bank rel, in fixed_music_dirs() order."""
    sub = _sub_of(rel)
    if not sub or not sub.endswith(('_a.zss', '_c.zss')):
        return []
    return [d / sub for d in fixed_music_dirs(ctx) if (d / sub).is_file()]


def fixed_music_path(ctx, rel):
    """the first fixed-layout candidate for rel, or None (pure)."""
    c = fixed_music_candidates(ctx, rel)
    return c[0] if c else None


def bank_source(ctx, rel):
    """The origin of the bytes media installs for the planned bank `rel` (Path), or None for XML2's own ('base')
    and unplanned banks (pure provider). A fixed music bank is copied byte for byte into
    <out>/_build/media_cache/music_fixed/ first and installed from there (that snapshot is the registry source);
    this returns the research file it came from. After media.run: the recorded choice
    (ctx.shared['sound_bank_sources']). Before it, the rule: an 'x1' music bank comes from the first
    fixed_music_dirs() entry that has it when music_mode is 'fixed', everything else from the plan's src.
    (media.run moves on to the next candidate, and finally to the plan's src, when a fixed bank fails its
    checks; an error when the plan's bank fails the engine check too. The recorded choice wins.)"""
    n = C.norm(rel)
    done = ctx.shared.get('sound_bank_sources')
    if done is not None and n in done:
        return Path(done[n])
    pe = ctx.planned_sound_banks().get(n)
    if not pe or pe['kind'] == 'base' or not pe.get('src'):
        return None
    if pe['kind'] == 'x1' and music_mode(ctx) == 'fixed':
        f = fixed_music_path(ctx, n)
        if f is not None:
            return f
    return Path(pe['src'])


# ============================================================================================ small helpers
def _deep_enabled(ctx):
    v = ctx.opt('media_deep', None)
    if v in (None, ''):
        v = os.environ.get(DEEP_ENV, '1')
    return str(v).strip().lower() not in ('0', 'off', 'no', 'false')


MAX_CHECK_WORKERS = 6                      # decode workers peak at ~0.8 GB each on the longest (nuke_c, 44.1 kHz)


def _jobs(ctx, n):
    return max(1, min(int(ctx.opt('jobs', 1) or 1), n, MAX_CHECK_WORKERS))


def _is_under(p, root):
    try:
        Path(p).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def _read_meta_json(ctx, name):
    p = ctx.build_dir / name
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _stat_key(p):
    return MM.stat_key(str(p)) if p is not None else None


def _stage(ctx, src: Path, name: str, data: bytes = None) -> Path:
    """Copy src into <out>/_build/<name> (build metadata: never swept, not a game file) unless the staged copy
    already has the same bytes, and return the staged path. The fixed music banks are installed from this
    snapshot so the registry source, the check cache and the installed bytes stay consistent even while
    research/sound/music0x20 is being regenerated, and validate V8 treats <out>/_build/media_cache sources as
    media-processed banks (keys must equal the plan bank's)."""
    dst = ctx.build_dir / name
    if data is None:
        data = Path(src).read_bytes()
    try:
        if dst.is_file() and dst.stat().st_size == len(data) and dst.read_bytes() == data:
            return dst
    except OSError:
        pass
    return ctx.write_meta(name, data)


# ============================================================================================ sound checks
def _layered_ok(bank, s):
    """None or an error string: a layered (0x20) stream must end after a complete layer-0 chunk (0x595d60)."""
    fl = s.raw[2]
    if not fl & MM.FLAG_LAYERED:
        return None
    ch, nsub = MM.sample_layout(fl)
    f = bank.files[s.u16(0)]
    nbytes = f.u32(4)
    frames = nbytes if ch == 2 else nbytes * 2          # headerless IMA: 4 bits per sample
    try:
        MM.engine_voice_frames(frames, ch, nsub)
    except MM.LayoutError as e:
        return str(e)
    return None


def _check_bank(data: bytes, rel: str):
    """strict parse + XML2-loader constraints. -> (bank or None, errors[], info{})."""
    errs = []
    try:
        b = zsnd.Bank(data, rel, strict=True)
    except zsnd.ZsndError as e:
        return None, [f'strict parse failed: {e}'], {}
    is_zsm = rel.lower().endswith('.zsm')
    if b.platform != 'pc':
        errs.append(f'magic {b.magic!r} is not ZSNDPC')
    if b.file_size != len(data):
        errs.append(f'file_size field {b.file_size} != actual {len(data)}')
    fmts = {b.file_format(f) for f in b.files}
    if fmts - {MM.IMA}:
        errs.append(f'file formats {sorted(fmts)}: XML2 decodes only IMA 0x6a '
                    f'({"raw-PCM path in .zsm is untested" if is_zsm else ".zss streams are always read as IMA"})')
    info = {'sounds': len(b.sounds), 'samples': len(b.samples), 'files': len(b.files), 'tracks': len(b.tracks),
            'bytes': len(data), 'stereo': 0, 'layered': 0, 'rates': {}}
    for s in b.samples:
        fl, rate = s.raw[2], s.u32(4)
        info['rates'][str(rate)] = info['rates'].get(str(rate), 0) + 1
        if fl & MM.FLAG_STEREO:
            info['stereo'] += 1
            if is_zsm:
                errs.append(f'sample {s.index}: stereo (0x02) in a .zsm (loader nBlockAlign=2, 0x5950c3)')
        if fl & MM.FLAG_LAYERED:
            info['layered'] += 1
            if is_zsm:
                errs.append(f'sample {s.index}: layered stream flag 0x20 in a .zsm')
            e = _layered_ok(b, s)
            if e:
                errs.append(f'sample {s.index}: {e}')
        if fl & MM.FLAG_8BIT:
            errs.append(f'sample {s.index}: 8-bit flag 0x04 (never valid for IMA)')
        if fl & ~(KNOWN_SAMPLE_FLAGS | MM.FLAG_8BIT) & 0xff:
            errs.append(f'sample {s.index}: unknown flag bits {fl:#x}')
        if not 0 < rate <= 0xffff:
            errs.append(f'sample {s.index}: rate {rate} does not fit the stream reader u16 (0x595acc)')
    for i, t in enumerate(b.tracks):
        blob = b.ztrk[i] if i < len(b.ztrk) else b''
        try:
            refs = ztrk.sound_refs(blob)
        except ztrk.ZtrkError as e:
            errs.append(f'track {i}: ZTRK does not parse: {e}')
            continue
        bad = [blob[o] for o in refs if blob[o] >= len(b.sounds)]
        if bad:
            errs.append(f'track {i}: sound refs {bad} out of range ({len(b.sounds)} sounds)')
    info['empty'] = not b.sounds and not b.tracks
    return b, errs, info


def _check_merged(ctx, merged, base_rel):
    """every XML2 entry of the replaced base bank is kept at its index with identical bytes and audio; its key too,
    except an entry the merge shadowed (issue #49: XML1's voice folders) under merge_zsnd.shadow_key."""
    p = ctx.base_index.path(base_rel)
    if p is None:
        return [f'no XML2 bank {base_rel} to compare with']
    try:
        base = zsnd.load(str(p), strict=False)
    except zsnd.ZsndError as e:
        return [f'XML2 bank {base_rel} unreadable: {e}']
    errs = []
    for tname in ('sounds', 'samples', 'tracks'):
        a, m = getattr(base, tname), getattr(merged, tname)
        if len(m) < len(a):
            errs.append(f'{tname}: merged has {len(m)} < XML2 {len(a)}')
            continue
        for i, e in enumerate(a):
            if m[i].hashes != e.hashes and (tname == 'samples' or m[i].hashes != [merge_zsnd.shadow_key(
                    os.path.basename(base_rel), '' if tname == 'sounds' else 't', i)]):
                errs.append(f'{tname}[{i}]: key changed')
                break
            if tname == 'sounds' and m[i].raw[:0x16] != e.raw[:0x16]:
                errs.append(f'{tname}[{i}]: entry bytes changed')
                break
            if tname == 'samples' and m[i].raw[:8] != e.raw[:8]:
                errs.append(f'{tname}[{i}]: entry bytes changed')
                break
    if len(merged.files) < len(base.files):
        errs.append(f'files: merged has {len(merged.files)} < XML2 {len(base.files)}')
    else:
        for i, f in enumerate(base.files):
            g = merged.files[i]
            if base.file_format(f) != merged.file_format(g) or base.file_bytes(f) != merged.file_bytes(g):
                errs.append(f'files[{i}]: XML2 audio changed')
                break
    for i in range(len(base.tracks)):
        if i < len(merged.ztrk) and i < len(base.ztrk) and \
                base.ztrk[i].rstrip(b'\0') != merged.ztrk[i].rstrip(b'\0'):
            errs.append(f'tracks[{i}]: XML2 ZTRK changed')
            break
    return errs


def _deep_music_checks(ctx, jobs):
    """jobs: [(rel, installed source Path, xbox Path)] -> {rel: media_music.check_bank result}. Results are cached
    in <out>/_build/media_cache/music_check.json keyed by the algorithm and both files' size + mtime."""
    cache_name = 'media_cache/music_check.json'
    cache = _read_meta_json(ctx, cache_name)
    results, todo = {}, []
    for rel, src, xsrc in jobs:
        key = [MM.ALGO, _stat_key(src), _stat_key(xsrc)]
        hit = cache.get(f'{rel}|{src}')
        if hit and hit.get('key') == key:
            results[rel] = hit['result']
        else:
            todo.append((rel, src, xsrc, key))
    if todo:
        n = _jobs(ctx, len(todo))
        ctx.log(f'checking {len(todo)} music banks against the Xbox originals with {n} worker processes '
                f'({len(results)} cached)')
        done = {}
        try:
            with ProcessPoolExecutor(max_workers=n) as ex:
                futs = {ex.submit(MM.check_job, str(src), str(xsrc)): rel for rel, src, xsrc, key in todo}
                for fu in as_completed(futs):
                    try:
                        done[futs[fu]] = fu.result()
                    except Exception as e:  # noqa: BLE001 - broken pool: rerun in-process below
                        ctx.log(f'{futs[fu]}: worker failed ({type(e).__name__}: {e}); retrying in-process')
        except (OSError, RuntimeError, ImportError) as e:
            ctx.log(f'music check worker pool unavailable ({type(e).__name__}: {e}); running in-process')
        for rel, src, xsrc, key in todo:
            r = done.get(rel) or MM.check_job(str(src), str(xsrc))
            results[rel] = r
            cache[f'{rel}|{src}'] = {'key': key, 'result': r}
        ctx.write_meta(cache_name, cache)
    return results


# ============================================================================================ sounds
def _install_sounds(ctx, detail):
    plan = ctx.planned_sound_banks()
    merged_root = ctx.research_path(MERGED_DIR)
    ima_root = ctx.research_path(IMA_DIR)
    mode = music_mode(ctx)
    deep = _deep_enabled(ctx)
    raw_mode = _music_mode_raw(ctx)
    if raw_mode not in _MODE_WORDS['fixed'] + _MODE_WORDS['ima']:
        ctx.warn(f'{MUSIC_ENV}={raw_mode!r} not understood (use fixed or ima); using {mode}')
    fdirs = fixed_music_dirs(ctx)
    prepared = _prepared(ctx)
    if prepared and (ctx.opt('music_dir', None) or os.environ.get(MUSIC_DIR_ENV, '')):
        ctx.warn(f'{MUSIC_DIR_ENV} is ignored in prepared mode: the music banks come from prepare stage P5 only')
    base_by_stem = {}
    for a in ctx.base_index.under('sounds/'):
        s, e = C.split_ext(a)
        if e.lower() in ('.zsm', '.zss'):
            base_by_stem.setdefault(Path(s).name.lower(), []).append(C.norm(a))
    items = sorted((r, v) for r, v in plan.items() if v['kind'] in ('x1', 'merged'))
    all_stems = sorted({v['bank'] for v in plan.values()})

    # ---- plan sanity (nothing is written for a bank that fails these)
    ok_items = []
    for rel, v in items:
        src = Path(v['src']) if v['src'] else None
        stem = v['bank']
        parts = rel.split('/')
        if src is None or not src.is_file():
            ctx.error(f'{rel}: planned source {src} is missing')
            continue
        if len(parts) != 5 or parts[:2] != ['sounds', 'eng'] or parts[2] != stem[0] or parts[3] != stem[1]:
            ctx.error(f'{rel}: not at sounds/eng/<c1>/<c2>/<bank> (XMen2.exe 0x592b00 two-letter rule)')
            continue
        if v['kind'] == 'x1':
            if stem in base_by_stem and not (v.get('frontend') and stem in C.FRONTEND_MUSIC):
                ctx.error(f'{rel}: XML2 ships bank {stem!r} ({base_by_stem[stem]}); refusing to install the '
                          f'unmerged XML1 bank over it')
                continue
            if stem in base_by_stem:
                ctx.note(f'{rel}: XML1\'s bank replaces XML2\'s {stem} (--frontend xml1: {C.FRONTEND_MUSIC[stem]}; '
                         f'XML2\'s bank holds only its music/{stem} sound)')
            if not _is_under(src, ima_root):
                ctx.error(f'{rel}: x1 bank source {src} is not under research/{IMA_DIR}')
                continue
        else:
            if not _is_under(src, merged_root):
                ctx.error(f'{rel}: merged bank source {src} is not under research/{MERGED_DIR}')
                continue
            for b in base_by_stem.get(stem, []):
                if b != rel:
                    if b.endswith('.zsm') and rel.endswith('.zss'):
                        ctx.error(f'{rel}: XML2 {b} stays in <out> and shadows the merged .zss (loader opens '
                                  f'.zsm first, 0x591380)')
                    else:
                        ctx.warn(f'{rel}: XML2 also ships {b} (kept; the loader prefers .zsm)')
        ok_items.append((rel, v, src))
    pref = {}
    for s in all_stems:
        pref.setdefault(s[:BANK_NAME_CHECK], []).append(s)
    for p, ss in pref.items():
        if len(ss) > 1:
            ctx.warn(f'banks {ss} share the first {BANK_NAME_CHECK} characters; XMen2.exe 0x5913c4 treats them '
                     f'as the same already-loaded bank')

    # ---- music banks: choose the source (fixed layout by default) and check it against the Xbox original.
    # Candidates per bank: every fixed_music_dirs() file (in order), then the plan's all_ima bank. A fixed candidate
    # is read once, parsed from those bytes, compared with the plan bank (keys / entries / rate 1:1 or 2:1),
    # snapshotted into <out>/_build/media_cache/music_fixed (the snapshot is what gets checked and installed) and
    # checked against the Xbox original; the first candidate that passes wins. The plan bank is the last resort.
    music = {}          # rel -> {kind: fixed|ima, src, origin, plan_src, layered, fixed_problems, check, why}
    source = {rel: src for rel, v, src in ok_items}
    refs = {}
    for rel, v, src in ok_items:
        if v['kind'] != 'x1' or not rel.endswith(('_a.zss', '_c.zss')):
            continue
        try:
            ref = zsnd.load(str(src))
        except zsnd.ZsndError as e:
            ctx.error(f'{rel}: plan source {src} does not parse: {e}')
            continue
        if not MM.is_music_bank(ref, rel):
            continue
        refs[rel] = ref
        cands = fixed_music_candidates(ctx, rel) if mode == 'fixed' else []
        music[rel] = {'kind': 'ima', 'src': src, 'plan_src': src, 'fixed_problems': [], 'cands': cands,
                      'layered': any(s.raw[2] & MM.FLAG_LAYERED for s in ref.samples)}
        if mode == 'fixed' and not cands:
            music[rel]['fixed_problems'].append(
                f'no fixed-layout bank {_sub_of(rel)} in {[str(d) for d in fdirs]}')

    def next_candidate(rel):
        """advance rel to its next structurally valid fixed candidate (staged); False when none is left."""
        row = music[rel]
        while row['cands']:
            fp = row['cands'].pop(0)
            try:
                data = fp.read_bytes()
                fb = zsnd.Bank(data, str(fp), strict=True)
                errs = [] if fb.platform == 'pc' else [f'magic {fb.magic!r}']
                errs += MM.structure_diff(fb, refs[rel])
                for a, b in zip(fb.samples, refs[rel].samples):
                    ra, rb = a.u32(4), b.u32(4)
                    if not 0 < ra <= 0xffff or rb not in (ra, 2 * ra):
                        errs.append(f'sample {b.index}: rate {ra} (reference {rb}); expected {rb} or {rb // 2}')
            except (OSError, zsnd.ZsndError) as e:
                errs = [f'unreadable: {e}']
            if errs:
                row['fixed_problems'] += [f'{fp}: {m}' for m in errs]
                continue
            # builder mode installs P5's bank itself (the prepare cache is immutable under the builder's cache lock)
            staged = fp if C.builder_mode(ctx.args) else _stage(ctx, fp, f'{STAGE_DIR}/{_sub_of(rel)}', data)
            row.update(kind='fixed', src=staged, origin=fp)
            source[rel] = staged
            return True
        if row['kind'] == 'fixed':          # the last fixed candidate failed: back to the plan's bank
            row.update(kind='ima', src=row['plan_src'])
            row.pop('origin', None)
            source[rel] = row['plan_src']
        return False

    for rel in sorted(music):
        next_candidate(rel)
    checks = {}
    xroot = ctx.x1_xbox / 'sounds' / 'zsds'
    if music and deep:
        def run_checks(rels):
            jobs = []
            for rel in rels:
                xs = xroot / _sub_of(rel)
                if xs.is_file():
                    jobs.append((rel, music[rel]['src'], xs))
                else:
                    music[rel]['check'] = {'ok': False, 'problems': [f'no Xbox original {xs} to check against'],
                                           'samples': []}
            for rel, r in _deep_music_checks(ctx, jobs).items():
                music[rel]['check'] = r
        pending = sorted(music)
        while pending:
            run_checks(pending)
            again = []
            for rel in pending:
                row = music[rel]
                if row['kind'] != 'fixed' or row['check'].get('ok'):
                    continue
                row['fixed_problems'] += [f'{row["origin"]}: {m}' for m in row['check']['problems']]
                row.setdefault('rejected_checks', []).append(row['check'])
                next_candidate(rel)          # next fixed candidate, or the plan bank (checked next round)
                again.append(rel)
            pending = again
        checks = {rel: row['check'] for rel, row in music.items()}
    for rel, row in sorted(music.items()):
        ok = (row.get('check') or {}).get('ok')
        if row['kind'] == 'fixed':
            if row['fixed_problems']:
                ctx.warn(f'{rel}: installed the fixed bank {row["origin"]} after rejecting earlier candidates: '
                         f'{"; ".join(row["fixed_problems"][:3])}')
            continue
        if mode == 'fixed' and prepared:
            # the prepare stage P5 made (and checked) every music bank: a missing or failing one is a broken
            # cache or a bug, never a reason to install the 1:1 bank (SPEC 27.6)
            ctx.error(f'{rel}: prepared mode: no music bank from prepare stage P5 plays correctly '
                      f'({"; ".join(row["fixed_problems"][:3]) or "none"}); the 1:1 all_ima bank is not a fallback '
                      f'here (delete the music stage from the prepare cache and rebuild)')
            continue
        if mode == 'fixed':
            why = '; '.join(row['fixed_problems'][:3])
            if ok:              # plain stereo bank: the 1:1 conversion plays correctly (voice 0 = the music)
                row['why'] = f'1:1 all_ima bank installed ({why}); it passes the engine check'
            elif ok is None:    # deep check disabled
                (ctx.error if row['layered'] else ctx.warn)(
                    f'{rel}: installing the 1:1 all_ima bank ({why})'
                    + (' - XMen2.exe plays its two layers as interleaved 8192-frame slices' if row['layered']
                       else ''))
            else:
                ctx.error(f'{rel}: no music bank that plays correctly through XMen2.exe ({why}); the 1:1 all_ima '
                          f'bank is installed and fails too: {"; ".join(row["check"]["problems"][:2])} '
                          f'(run tools/fix_music.py, or set {MUSIC_DIR_ENV})')
        elif ok is False:
            ctx.warn(f'{rel}: {MUSIC_ENV}=ima - the 1:1 bank does not play as XML1 through XMen2.exe: '
                     f'{"; ".join(row["check"]["problems"][:2])}')
    if music and not deep:
        ctx.warn(f'{DEEP_ENV}=0: {len(music)} music banks installed without the decode-based layout check')

    # ---- install + verify
    installed, banks, sources = set(), [], {}
    dual = {}
    for rel, v, plan_src in ok_items:
        stem = v['bank']
        dual.setdefault(stem, []).append(rel)
        src = source[rel]
        actual = ctx.copy_file(src, rel)
        out_bytes = (ctx.out / actual).read_bytes()
        b, errs, info = _check_bank(out_bytes, rel)
        if out_bytes != Path(src).read_bytes():
            errs.append(f'installed bytes differ from {src}')
        if b is not None and rel in music:
            h = zhash.elf_hash(f'music/{stem}')
            if not any(h in s.hashes for s in b.sounds):
                errs.append(f"'music/{stem}' (XMen2.exe 0x477690 builds music/<soundfile>_a|_c) is not a key of "
                            f"this bank")
        if v['kind'] == 'merged' and b is not None:
            ext = rel.rsplit('.', 1)[-1]
            base_rels = [x for x in base_by_stem.get(stem, []) if x.rsplit('.', 1)[-1] == ext] \
                or base_by_stem.get(stem, [])
            for br in base_rels:
                errs += [f'merged vs XML2 {br}: {m}' for m in _check_merged(ctx, b, br)]
        for m in errs:
            ctx.error(f'{actual}: {m}')
        n = C.norm(actual)
        installed.add(n)
        origin = (music.get(rel) or {}).get('origin') or src
        sources[n] = str(origin)
        row = {'rel': actual, 'kind': v['kind'], 'src': str(src), 'origin': str(origin), 'plan_src': str(plan_src),
               'errors': errs,
               **info}
        if rel in music:
            m = music[rel]
            row['music'] = {'source': m['kind'], 'layered': m['layered'],
                            'check_ok': (m.get('check') or {}).get('ok'),
                            'check': (m.get('check') or {}).get('samples'),
                            'problems': (m.get('check') or {}).get('problems'),
                            'fixed_problems': m['fixed_problems'], 'why': m.get('why'),
                            'rates': sorted({int(r) for r in info.get('rates', {})})}
        banks.append(row)
        ctx.count('banks_x1' if v['kind'] == 'x1' else 'banks_merged')
        ctx.count('bank_bytes', len(out_bytes))
        ctx.count('ztrk_tracks', info.get('tracks', 0))
        if info.get('empty'):
            ctx.count('banks_empty')

    # ---- report
    nfix = sum(1 for m in music.values() if m['kind'] == 'fixed')
    nlay = sum(1 for m in music.values() if m['layered'])
    ctx.set_count('music_banks', len(music))
    ctx.set_count('music_banks_fixed', nfix)
    ctx.set_count('music_banks_checked', len(checks))
    ctx.set_count('music_banks_check_ok', sum(1 for r in checks.values() if r.get('ok')))
    corr = [c[i][i] for r in checks.values() if r.get('ok') for s in r.get('samples', [])
            for c in [s.get('corr') or []] for i in range(len(c))]
    rates = sorted({r for b in banks if b.get('music') and b['music']['source'] == 'fixed'
                    for r in b['music']['rates']})
    flat = sorted(rel for rel, m in music.items() if any(s.get('flattened') for s in
                                                        (m.get('check') or {}).get('samples') or []))
    if mode == 'fixed':
        fell_back = sorted(rel for rel, m in music.items() if m['kind'] != 'fixed')
        ctx.note(f'music: {nfix}/{len(music)} XML1 music banks ({nlay} layered combat banks) installed from '
                 f'{sorted({str(Path(m["origin"]).parent.parent.parent) for m in music.values() if m.get("origin")})} '
                 f'(tools/fix_music.py: layers re-interleaved at XMen2.exe\'s 8192-frame chunks; rates '
                 f'{rates}) instead of the plan\'s all_ima 1:1 banks, whose layered streams XMen2.exe plays as '
                 f'alternating slices of both layers (12 of 29 even end inside layer 0). Checked against the Xbox '
                 f'originals by engine simulation: {sum(1 for r in checks.values() if r.get("ok"))}/{len(checks)} '
                 f'installed banks pass' + (f', voice~layer correlation min {min(corr):.3f}' if corr else '')
                 + (f'; flattened (0x20 cleared): {flat}' if flat else '')
                 + (f'; 1:1 all_ima kept for {len(fell_back)}: {fell_back[:10]}{" ..." if len(fell_back) > 10 else ""}'
                    if fell_back else '') + '. '
                 f'{MUSIC_ENV}=ima installs the all_ima banks instead (A/B only).')
    else:
        bad = sum(1 for r in checks.values() if not r.get('ok'))
        ctx.warn(f'music: {MUSIC_ENV}=ima - {len(music)} XML1 music banks installed 1:1 from research/{IMA_DIR} '
                 f'at 44.1 kHz; {bad} of them fail the XMen2.exe layout check (combat banks play interleaved '
                 f'slices of both layers)')
    empty = [x['rel'] for x in banks if x.get('empty')]
    if empty:
        ctx.note(f'{len(empty)} XML1 banks are empty on the disc and installed as empty PC banks (all tables at '
                 f'0x64, counts 0), as the plan (and characters\' sounddir choice) expects: '
                 f'{", ".join(Path(e).name for e in empty)}. XMen2.exe\'s bank relocation 0x594e50 guards every '
                 f'table loop with count>0 and the per-sample loop ends at count 0 (0x595064), so they load as '
                 f'"no sounds", as on the Xbox.')
    for stem, rels in sorted(dual.items()):
        if len(rels) > 1:
            same = len({(ctx.out / ctx.out_index.get(r)).read_bytes() for r in rels}) == 1
            ctx.note(f'bank {stem} exists as {", ".join(Path(r).name for r in rels)} (as on the XML1 disc); the '
                     f'loader opens only the .zsm (0x591380); contents {"identical" if same else "DIFFER"}')
    ctx.note('XML1 sounds/badaudio.wav is not installed: XML2 ships its own Sounds/badaudio.wav (kept)')
    ctx.set_count('sound_banks_installed', len(installed))
    detail['sounds'] = {'music_mode': mode, 'deep_check': deep, 'banks': banks}
    return installed, sources


# ============================================================================================ movies
def _adx_header(head):
    """CRI ADX header fields or None: {encoding, block, bits, channels, rate, samples} (samples: total samples per
    channel, big-endian u32 at +12; samples / rate = the stream length, SPEC 21 C.4.1)."""
    if len(head) < 12 or head[0] != 0x80 or head[1] != 0x00:
        return None
    return {'encoding': head[4], 'block': head[5], 'bits': head[6], 'channels': head[7],
            'rate': int.from_bytes(head[8:12], 'big'),
            'samples': int.from_bytes(head[12:16], 'big') if len(head) >= 16 else None}


def movie_duration(ctx, x1_name):
    """Length in seconds of an XML1 movie (pure provider, SPEC 21 C.4.1): total samples / rate of the C0 ADX
    stream of xml1_xbox/movies/ntsc/**/<name>.sfd (the method matches XML2's own review_paths durations within
    0.3 s: cine01 149.72 vs 149.44, i106 52.28 vs 52.28). Takes the XML1 name ('r102', 'I101'). None when the
    movie or its ADX header is missing. Works with --no-movies (reads the disc copy)."""
    n = C.norm(x1_name).rsplit('/', 1)[-1]
    if n.endswith('.sfd'):
        n = n[:-4]
    with _lock:
        cache = _duration_cache.setdefault(str(ctx.x1_xbox), {})
        if n in cache:
            return cache[n]
    p = next((q for name, q, _ in _x1_movies(ctx) if name == n), None)
    dur = None
    if p is not None:
        c0 = (movie_facts(ctx, p)[1].get('adx') or {}).get('c0') or {}
        if c0.get('rate') and c0.get('samples'):
            dur = round(c0['samples'] / c0['rate'], 2)
    with _lock:
        cache[n] = dur
    return dur


def _sofdec_info(path: Path, limit=SOFDEC_LIMIT):
    """MPEG-1 program-stream walk of the first `limit` bytes of a movie file (sofdec_info_bytes)."""
    with open(path, 'rb') as fh:
        b = fh.read(limit)
    return sofdec_info_bytes(b, path.stat().st_size)


def sofdec_info_bytes(b: bytes, size: int) -> dict:
    """MPEG-1 program-stream walk of a movie's first bytes (after research/sweep/movies.py): pack type,
    SofdecStream signature, video geometry / frame-rate code, per-stream kind (video / adx / aix / hex) and the
    ADX header of each ADX stream. size = the whole file's size. (prepare P1 runs it on the disc image for
    movies.json.)"""
    import struct
    r = {'size': size, 'sofdec': b'SofdecStream' in b[:0x4000]}
    r['pack'] = ('mpeg1' if b[:4] == b'\x00\x00\x01\xba' and (b[4] & 0xF0) == 0x20 else
                 'mpeg2' if b[:4] == b'\x00\x00\x01\xba' and (b[4] & 0xC0) == 0x40 else 'unknown')
    i = b.find(b'\x00\x00\x01\xb3')
    if i >= 0 and i + 8 <= len(b):
        r['video'] = '%dx%d' % ((b[i + 4] << 4) | (b[i + 5] >> 4), ((b[i + 5] & 0xF) << 8) | b[i + 6])
        r['frame_rate_code'] = b[i + 7] & 0x0F
    pos, streams, adx = 0, {}, {}
    while pos + 6 <= len(b) and b[pos:pos + 3] == b'\x00\x00\x01':
        sid = b[pos + 3]
        if sid == 0xba:
            pos += 12 if (b[pos + 4] & 0xF0) == 0x20 else 14 + (b[pos + 13] & 7)
            continue
        if sid == 0xb9:
            break
        ln = struct.unpack_from('>H', b, pos + 4)[0]
        payload = b[pos + 6:pos + 6 + ln]
        if sid not in streams:
            q = 0
            if 0xc0 <= sid <= 0xef:
                while q < len(payload) and payload[q] == 0xff:
                    q += 1
                if q < len(payload) and (payload[q] & 0xC0) == 0x40:
                    q += 2
                if q < len(payload):
                    q += {0x2: 5, 0x3: 10}.get(payload[q] >> 4, 1)
            head = payload[q:q + 0x400]
            cofs = int.from_bytes(head[2:4], 'big') if len(head) >= 4 else 0
            if 0xe0 <= sid <= 0xef:
                kind = 'video'
            elif head[:2] == b'\x80\x00' and head[cofs - 2:cofs + 4] == b'(c)CRI':   # ADX: "(c)CRI" at ofs-2
                kind = 'adx'
                adx['%02x' % sid] = _adx_header(head)
            elif head[:4] == b'AIXF':
                kind = 'aix'
            else:
                kind = head[:8].hex()
            streams[sid] = kind
        pos += 6 + ln
    r['streams'] = {'%02x' % k: v for k, v in sorted(streams.items())}
    r['adx'] = adx
    return r


def _movies_index(ctx) -> dict:
    """{normcase(str(path)): row} of the prepared disc's movies.json (Sources.movies_index; prepare P1 writes it
    from the disc image: name, path below x1_xbox, size, Sofdec facts), or {} (developer mode)."""
    ip = getattr(ctx.sources, 'movies_index', None)
    if not ip:
        return {}
    key = (str(ip), str(ctx.x1_xbox))
    with _lock:
        if key not in _movies_index_cache:
            try:
                rows = json.loads(Path(ip).read_text(encoding='utf-8'))
            except (OSError, ValueError):
                rows = []
            _movies_index_cache[key] = {os.path.normcase(str(ctx.x1_xbox / r['path'])): r for r in rows}
        return _movies_index_cache[key]


def x1_movie_files(ctx):
    """[Path] of the XML1 NTSC movies (unsorted): the .sfd files under x1_xbox/movies/ntsc, or - when a prepared
    disc was made without them (a --no-movies build; prepare P1) - the paths its movies.json lists, whose facts
    movie_facts() serves. A --no-movies build reads only names, sizes and headers, so both give the same build."""
    root = ctx.x1_xbox.joinpath(*X1_MOVIE_DIR)
    if root.is_dir():
        return [Path(dp) / f for dp, _, fs in os.walk(root) for f in fs if f.lower().endswith('.sfd')]
    return [ctx.x1_xbox / r['path'] for r in _movies_index(ctx).values()]


def movie_facts(ctx, p):
    """(size, _sofdec_info) of an XML1 movie: read from the file, else from movies.json (x1_movie_files)."""
    p = Path(p)
    if p.is_file():
        return p.stat().st_size, _sofdec_info(p)
    r = _movies_index(ctx).get(os.path.normcase(str(p)))
    if r is None:
        raise FileNotFoundError(p)
    return r['size'], r['info']


def _x1_movies(ctx):
    """[(name, Path, (c1, c2))] of the XML1 NTSC movies, sorted."""
    root = ctx.x1_xbox.joinpath(*X1_MOVIE_DIR)
    out = []
    for p in x1_movie_files(ctx):
        sub = p.relative_to(root).parts
        out.append((p.stem.lower(), p, tuple(x.lower() for x in sub[:-1])))
    return sorted(out)


def _xml2_movie_formats(ctx):
    """{(video, frame_rate_code, c0 adx channels, c0 adx rate)} over XML2's own movies (base install, read)."""
    fmts, rows = set(), {}
    for k in sorted(ctx.base_index.keys()):
        if k.startswith('movies/') and k.endswith('.sfd'):
            info = _sofdec_info(ctx.base_index.path(k))
            c0 = info['adx'].get('c0') or {}
            fmts.add((info.get('video'), info.get('frame_rate_code'), c0.get('channels'), c0.get('rate')))
            rows[k] = info
    return fmts, rows


def _same_file(a: Path, b: Path, chunk=8 << 20):
    if a.stat().st_size != b.stat().st_size:
        return False
    with open(a, 'rb') as fa, open(b, 'rb') as fb:
        while True:
            x, y = fa.read(chunk), fb.read(chunk)
            if x != y:
                return False
            if not x:
                return True


def _install_movies(ctx, detail):
    no_movies = bool(ctx.opt('no_movies'))
    movies = _x1_movies(ctx)
    if not movies:
        ctx.error(f'no XML1 movies under {ctx.x1_xbox.joinpath(*X1_MOVIE_DIR)}')
    x2_fmts, x2_rows = _xml2_movie_formats(ctx)
    verify_name = 'media_cache/movie_verify.json'
    verified = _read_meta_json(ctx, verify_name)
    renames, rows, seen = {}, [], {}
    c1_kinds = {}
    for name, p, sub in movies:
        new = movie_name(ctx, name)
        if new != name:
            renames[name] = new
        if name in seen:
            ctx.error(f'XML1 movie {name} exists twice ({seen[name]}, {p}); only the first is installed')
            continue
        seen[name] = p
        if sub != (name[0], name[1]):
            ctx.warn(f'{p}: not in the <c1>/<c2> directory of its name; installed by its name')
        dst = movie_rel(new)
        size, info = movie_facts(ctx, p)
        row = {'name': name, 'new': new, 'src': str(p), 'rel': dst, 'size': size}
        rows.append(row)
        if dst in ctx.base_index:
            ctx.error(f'{dst}: would overwrite an XML2 movie; not installed')
            row['status'] = 'refused'
            continue
        row['info'] = info
        if not info['sofdec'] or info['pack'] != 'mpeg1' or 'e0' not in info['streams'] or \
                info['streams'].get('c0') != 'adx':
            ctx.error(f'{p}: not a Sofdec MPEG-1 stream with video E0 + ADX audio C0 ({info}); not installed')
            row['status'] = 'refused'
            continue
        c0 = info['adx'].get('c0') or {}
        fmt = (info.get('video'), info.get('frame_rate_code'), c0.get('channels'), c0.get('rate'))
        if x2_fmts and fmt not in x2_fmts:
            ctx.warn(f'{p}: video/C0 format {fmt} differs from every XML2 movie {sorted(map(str, x2_fmts))}')
        c1 = info['streams'].get('c1', 'none')
        c1_kinds[c1] = c1_kinds.get(c1, 0) + 1
        if no_movies:
            row['status'] = 'skipped (--no-movies)'
            continue
        actual = ctx.copy_file(p, dst)
        q = ctx.out / actual
        key = [_stat_key(p), _stat_key(q)]
        if verified.get(actual) != key:
            if not _same_file(p, q):
                ctx.error(f'{actual}: copy differs from {p}')
                verified.pop(actual, None)
            else:
                verified[actual] = key
        row['rel'] = actual
        row['status'] = 'copied'
        ctx.count('movies_copied')
        ctx.count('movie_bytes', row['size'])
    if not no_movies:
        ctx.write_meta(verify_name, verified)
    if renames:
        ctx.set_count('movies_renamed', len(renames))
        ctx.note(f'XML1 movies renamed because XML2 ships the same names: '
                 f'{", ".join(f"{a}->{b}" for a, b in sorted(renames.items()))}. '
                 + ('--frontend xml1: the generated menus/intro_normal.py and the XML1 review_paths (frontend) use '
                    'the new names (SPEC 21).' if C.frontend_mode(ctx) == 'xml1' else
                    'XML1 references them only from menus/intro_{demo,e3,normal}.py (not installed; XML2\'s '
                    'intro_normal.py keeps playing XML2\'s i101-i107) and data/review_paths.eng (not ported).'))
    if no_movies:
        ctx.note(f'--no-movies: {len(rows)} XML1 movies not copied (subtitles are still written)')
    else:
        ctx.note(f'{sum(1 for r in rows if r.get("status") == "copied")} XML1 movies copied byte for byte (full '
                 f'compare) with their extra C1 audio stream (C1 kinds: {c1_kinds}); video and C0 ADX match XML2\'s '
                 f'movies {sorted(map(str, x2_fmts))}. In-game evidence that XML2\'s CRI player streams them: the '
                 f'loopback recording research/overlays/r102_movie.wav matches r102\'s C0 ADX track at r=0.96 '
                 f'(tools/audio_match.py; video not verified offline).')
    ctx.note('XML1 PAL movies (xml1_xbox/movies/pal) are not installed: XML2 PC ships only movies/ntsc/eng '
             '(XMen2.exe takes movies/pal/ only when its PAL flag is set, 0x57d15d, and then has no XML2 movies '
             'either)')
    detail['movies'] = rows
    detail['xml2_movies'] = x2_rows
    return renames, {r['name'] for r in rows}


# ============================================================================================ subtitles
def _fmt_seconds(x: float) -> str:
    s = f'{x:.3f}'.rstrip('0').rstrip('.')
    return s or '0'


def _install_subtitles(ctx, detail, movie_names):
    rels = [r for r in ctx.x1_rels('movies/') if r.endswith('.eng') and r.count('/') == 1]
    skipped_lang = [r for r in ctx.x1_rels('movies/') if r.endswith(('.fre', '.ger')) and r.count('/') == 1]
    rows = []
    for rel in rels:
        name = C.split_ext(rel)[0].rsplit('/', 1)[-1]
        new = movie_name(ctx, name)
        src = ctx.x1_path(rel)
        row = {'name': name, 'new': new, 'src': str(src), 'has_movie': name in movie_names}
        rows.append(row)
        root = ctx.read_x1_xml(rel)
        if root is None:
            ctx.warn(f'{rel}: empty subtitle file; nothing written')
            row['status'] = 'empty'
            continue
        if root.tag.lower() != 'subtitles':
            ctx.error(f'{rel}: root <{root.tag}> is not <SubTitles>; not written')
            row['status'] = 'bad root'
            continue
        if root.tag != 'SubTitles':
            ctx.warn(f'{rel}: root tag {root.tag!r} normalised to XML2\'s SubTitles')
            root.tag = 'SubTitles'
        items, bad = [], 0
        for el in list(root):
            try:
                t, life = float(el.get('time')), float(el.get('life'))
            except (TypeError, ValueError):
                t = life = None
            if el.tag.lower() != 'item' or t is None or life is None or life <= 0 or not el.get('text'):
                ctx.warn(f'{rel}: dropped malformed <{el.tag} {dict(el.attrib)}>')
                root.remove(el)
                bad += 1
                continue
            extra = sorted(set(el.attrib) - {'time', 'life', 'text'})
            if extra:
                ctx.warn(f'{rel}: <item> attributes {extra} are not in XML2\'s subtitle schema (kept)')
            el.tag = 'item'
            items.append((t, life, el))
        if not items:
            ctx.error(f'{rel}: no usable <item>; not written')
            row['status'] = 'no items'
            continue
        if any(items[i][0] > items[i + 1][0] for i in range(len(items) - 1)):
            ctx.warn(f'{rel}: item times are not ascending; kept in file order')
        src_items = [(el.get('time'), el.get('life'), el.get('text')) for _, _, el in items]
        clamped = 0
        if CLAMP_SUBTITLE_OVERLAPS:
            for i in range(len(items) - 1):
                t, life, el = items[i]
                gap = items[i + 1][0] - t
                if gap > 0 and life > gap:
                    el.set('life', _fmt_seconds(gap))
                    clamped += 1
        actual = ctx.write_xmlb(f'Movies/{new}', root, ('.XMLB', '.engb'), source=src)
        for a in actual:            # re-decode what is on disk: schema, attribute order, items vs the source
            back = C.decode_xmlb((ctx.out / a).read_bytes())
            probs = C.xmlb_attr_problems(back)
            got = [(el.get('time'), el.get('life'), el.get('text')) for el in back]
            diff = [i for i, (g, s) in enumerate(zip(got, src_items))
                    if g[0] != s[0] or g[2] != s[2] or
                    not (g[1] == s[1] or (CLAMP_SUBTITLE_OVERLAPS and float(g[1]) <= float(s[1])))]
            if back.tag != 'SubTitles' or len(back) != len(items) or probs or diff or \
                    any(el.tag != 'item' for el in back):
                ctx.error(f'{a}: re-decode check failed ({back.tag}, {len(back)}/{len(items)} items, attr '
                          f'problems {probs[:2]}, differing items {diff[:5]})')
        row.update({'status': 'written', 'rels': actual, 'items': len(items), 'dropped': bad,
                    'lives_clamped': clamped})
        ctx.count('subtitles')
        ctx.count('subtitle_items', len(items))
        ctx.count('subtitle_lives_clamped', clamped)
    no_sub = sorted(movie_names - {r['name'] for r in rows})
    orphan = sorted(r['name'] for r in rows if not r['has_movie'])
    ctx.note(f'{sum(1 for r in rows if r.get("status") == "written")} movie subtitle files written as '
             f'Movies/<name>.XMLB+.engb (English text in both); lives clamped to the next line: '
             f'{sum(r.get("lives_clamped", 0) for r in rows)}. Movies without subtitles (as on the XML1 disc; '
             f'XML2\'s own i101-i107 have none either): {no_sub}. Subtitles without an XML1 NTSC movie (written '
             f'anyway, harmless): {orphan}.')
    if skipped_lang:
        ctx.note(f'{len(skipped_lang)} .fre/.ger movie subtitle files skipped (English build)')
    detail['subtitles'] = rows


# ============================================================================================ cross checks
_START_MOVIE = re.compile(r'''\bstartMovie\s*\(\s*["']([^"']+)["']''')
_DEAD_MOVIES = {'test1', 'test3', 'blackbird_leave_mansion'}     # dead missions/*_start.py (validate V9 list)


def _check_movie_refs(ctx, detail, renames, movie_names):
    """startMovie literals of every script another module installed (or carried over) this build."""
    refs = {}
    scripts = [e['rel'] for e in ctx.registry.entries.values()
               if e['rel'].lower().endswith('.py') and e['owner'] != MODULE]
    for rel in scripts:
        p = ctx.out / rel
        if not p.is_file():
            continue
        for m in _START_MOVIE.finditer(p.read_text(encoding='latin-1')):
            refs.setdefault(m.group(1), []).append(rel)
    if not scripts:
        ctx.note('no installed scripts in the registry (scripts module not run); startMovie cross-check skipped')
    base_names = _base_movie_names(ctx)
    missing, dead = {}, {}
    for name, rels in sorted(refs.items()):
        n = C.norm(name)
        if n in renames:
            x1_users = [r for r in rels if not C.norm(r).startswith('scripts/menus/intro_')]
            if x1_users:
                ctx.error(f'startMovie("{name}") in {sorted(set(x1_users))[:5]} plays XML2\'s {n}.sfd; XML1\'s '
                          f'movie is installed as {renames[n]} (rewrite the call)')
        elif n not in movie_names and n not in base_names and n not in set(renames.values()):
            (dead if n in _DEAD_MOVIES else missing)[name] = sorted(set(rels))
    if dead:
        ctx.note(f'startMovie names that never existed on the XML1 disc, in dead developer scripts '
                 f'(validate V9 allowlist): { {k: v[:2] for k, v in dead.items()} }')
    for name, rels in missing.items():
        ctx.warn(f'startMovie("{name}") in {rels[:3]}: no such movie on the XML1 disc or in XML2')
    unref = sorted(n for n in movie_names if n not in {C.norm(k) for k in refs}) if scripts else []
    if unref:
        ctx.note(f'XML1 movies no installed script plays (review / front-end only): {unref}')
    detail['movie_refs'] = {'scripts_scanned': len(scripts), 'refs': {k: sorted(set(v)) for k, v in refs.items()},
                            'missing': missing, 'dead': dead, 'unreferenced': unref}


_ATTR = re.compile(r'\b(soundfile|ambientmusic|combatmusic|intromusic)\s*=\s*"([^"]*)"', re.I)


def _zone_music(ctx, detail, music_rows):
    """soundfile bank coverage of every XML1 zone + the world music attributes XML1's engine never read."""
    per_sf, overrides = {}, {}
    for z in ctx.x1_zones():
        p = None
        for ext in ('.eng', '.xml'):
            p = ctx.x1_path(f'maps/{z}{ext}')
            if p is not None:
                break
        if p is None:
            continue
        text = p.read_bytes().decode('latin-1')
        for m in _ATTR.finditer(text):
            k, v = m.group(1).lower(), m.group(2)
            if k == 'soundfile':
                per_sf.setdefault(v, []).append(z)
            else:
                overrides.setdefault(z, {})[k] = v
    cover = {}
    for sf, zones in sorted(per_sf.items(), key=lambda kv: kv[0].lower()):
        banks = {s: ctx.sound_bank_rel(f'{sf.lower()}_{s}') for s in ZONE_SUFFIXES}
        cover[sf] = {'zones': sorted(set(zones)), 'banks': banks, 'len_ok': len(sf) < 10,
                     'music': {s: (music_rows.get(banks[s]) or {}).get('kind') for s in 'ac' if banks[s]}}
    none = {sf: c['zones'] for sf, c in cover.items() if not any(c['banks'].values())}
    no_music = {sf: c['zones'] for sf, c in cover.items() if any(c['banks'].values())
                and not (c['banks']['a'] or c['banks']['c'])}
    long_sf = {sf: c['zones'] for sf, c in cover.items() if not c['len_ok']}
    if long_sf:
        ctx.warn(f'zone soundfiles of 10+ characters (XMen2.exe 0x5920cb aborts zone sound loading): {long_sf}')
    if none:
        ctx.note(f'zone soundfiles with no bank on the XML1 disc (zones play only x_common/x_voice/character '
                 f'sounds): { {k: v[:4] for k, v in none.items()} }')
    if no_music:
        ctx.note(f'zone soundfiles without _a/_c music banks: { {k: v[:4] for k, v in no_music.items()} }')
    if overrides:
        ctx.note(f'{len(overrides)} XML1 zones carry world ambientmusic/combatmusic/intromusic attributes '
                 f'({sorted(overrides)[:8]}...). They are dead data in XML1 as well: default.xbe contains none of '
                 f'those strings (nor "%smusic"; only music/, music/music_cues/ and music/menu_a) and builds zone '
                 f'music like XMen2.exe, "music/" + soundfile + "_a"/"_c" (XMen2.exe 0x477690). Nothing is lost; '
                 f'these zones play <soundfile>_a/_c on both platforms.')
    detail['zone_soundfiles'] = cover
    detail['zone_music_attributes'] = overrides
    _zone_bank_load(ctx, detail, per_sf)


BANK_SLOTS = 64          # XMen2.exe 0x594e50: 0x1200 / 0x48 bank slots at 0x804348; no free slot -> write to [0+4]
PARTY = 4


def _zone_bank_load(ctx, detail, per_sf):
    """Worst-case number of banks a zone keeps loaded: x_common + x_voice, <soundfile>_{m,a,c,v,d}, one sounddir bank
    per distinct character of its CHR / spawners (XML1 herostat+npcstat sounddir), plus a 4-hero party. XMen2.exe
    has 64 bank slots and does not check for a free one (0x594e88 falls through with slot = NULL)."""
    sd = {}
    for f in ('data/npcstat.eng', 'data/herostat.eng'):
        try:
            root = ctx.read_x1_xml(f)
        except KeyError:
            continue
        for el in (root.iter() if root is not None else []):
            if el.get('name') and el.get('sounddir'):
                sd[el.get('name').lower()] = el.get('sounddir').lower()
    zone_sf = {z: sf for sf, zs in per_sf.items() for z in zs}
    try:
        zinfo = ctx.zones_info
    except (OSError, ValueError):
        zinfo = {}
    rows = {}
    for z, info in zinfo.items():
        chars = {c.lower() for c in (info.get('chr_characters') or []) + (info.get('spawner_characters') or [])
                 if isinstance(c, str)}
        banks = {sd[c] for c in chars if c in sd and ctx.sound_bank_rel(sd[c])}
        sf = zone_sf.get(z)
        zb = sum(1 for s in ZONE_SUFFIXES if sf and ctx.sound_bank_rel(f'{sf.lower()}_{s}'))
        rows[z] = 2 + zb + len(banks) + PARTY
    worst = sorted(rows.items(), key=lambda kv: -kv[1])[:5]
    over = {z: n for z, n in rows.items() if n > BANK_SLOTS - 8}
    if over:
        ctx.warn(f'zones that may load more than {BANK_SLOTS - 8} of XMen2.exe\'s {BANK_SLOTS} sound-bank slots '
                 f'(0x594e50 has no full-table check): {over}')
    ctx.set_count('max_banks_per_zone', worst[0][1] if worst else 0)
    detail['zone_bank_load'] = {'slots': BANK_SLOTS, 'worst': worst, 'per_zone': rows}


# ============================================================================================ entry point
def run(ctx):
    detail = {}
    for k in ('banks_x1', 'banks_merged', 'movies_copied', 'subtitles', 'movie_bytes'):
        ctx.set_count(k, 0)             # SPEC.md 5.4 counts, present even when zero (--no-movies)
    installed, sources = _install_sounds(ctx, detail)
    ctx.shared['sound_banks_installed'] = installed
    ctx.shared['sound_bank_sources'] = sources
    music_rows = {C.norm(b['rel']): {'kind': b['music']['source']} for b in detail['sounds']['banks']
                  if b.get('music')}
    renames, movie_names = _install_movies(ctx, detail)
    ctx.shared['movie_renames'] = dict(renames)
    _install_subtitles(ctx, detail, movie_names)
    _check_movie_refs(ctx, detail, renames, movie_names)
    _zone_music(ctx, detail, music_rows)
    ctx.defer('lossless pcm_zsm alternative for .zsm banks (research/sound/out/pcm_zsm has only nyc1_d/m and '
              'grso_m; raw-PCM .zsm path 0x595141 unexercised by XML2): orchestrator decision after in-game A/B')
    ctx.write_meta('media_detail.json', detail)
