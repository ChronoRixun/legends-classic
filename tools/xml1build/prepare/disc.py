"""xml1build.prepare.disc - prepare stage P1 `disc` (BUILDER_DESIGN.md 1.1, 1.5; SPEC.md 27.3).

Replaces tools/xdvdfs_extract.py + the unzip of z/assetsfb.zip nobody scripted + tools/fb_unpack.py. Reads the
XML1 Xbox disc image in place (image.py: Redump XGD1 image or XISO) and writes, into <cache>/<disc_id>/disc/:

  xbox/default.xbe, xbox/sounds/zsds/**, xbox/movies/ntsc/**   byte copies of the disc files the build reads
                                                               (= those files of today's xml1_xbox/); the 648 MB
                                                               of movies only when the build wants them (movies=True,
                                                               the default; added later when a movies build needs
                                                               them: add_movies)
  assets/**          every member of z/assetsfb.zip except the .fb bundles (= xml1_assets/ minus its 875 bundles)
  loose/**           the bundles unpacked straight from the zip, never written as .fb files, with fb_unpack's rules
                     (prepare/fb.py): Windows glob order, lower-case names, the first bundle carrying a name wins
                     (= xml1_loose/)
  loose/_fb_manifest.json   bundle -> [[name, type], ...] exactly as fb_unpack wrote it on Windows (json indent=1,
                     CRLF line ends: it ran in text mode there)
  movies.json        the NTSC movies' names, disc paths, sizes and Sofdec / ADX facts (media.sofdec_info_bytes, read
                     from the image), always: a --no-movies build reads only these facts (media.x1_movie_files /
                     movie_facts), so it needs no movie files
  stage.json         the cache key, the disc's identity, counts, conflicts, timings, movies (bool)

Identification (identify): default.xbe's certificate title ID must be 0x4156001E (E_ISO_WRONG_GAME), and
default.xbe, z/assetsfb.zip, sounds/zsds/** and movies/ntsc/**.sfd must exist (E_ISO_INCOMPLETE: a demo disc or
a bad rip). Reading every zip member checks its CRC-32 (a damaged dump fails with E_ISO_READ).

Not copied (never read by the pipeline): movies/pal, media/*.bin, OptionsImage.xpr, sounds/badaudio.wav (the zip's
copy is in assets/), alchemy.ini, build.ini, and z/assetsfb.zip itself (its contents are assets/ + loose/)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import zipfile
import zlib
from pathlib import Path

from . import PrepareError, check_cancel, digest, fb, image, publish, read_stage, rename, rmtree, xbe

STAGE = 'disc'
VERSION = 1
LOOSE, ASSETS, XBOX = 'loose', 'assets', 'xbox'
MANIFEST = '_fb_manifest.json'
MOVIES_JSON = 'movies.json'
XBE_PATH = 'default.xbe'
ZIP_PATH = 'z/assetsfb.zip'
MOVIE_DIR = 'movies/ntsc'
DISC_DIRS = ('sounds/zsds', MOVIE_DIR)              # copied into xbox/ as they are on the disc (movies: optional)
NEWLINE = '\r\n'                                     # fb_unpack.py wrote the manifest in text mode on Windows


def _is_bundle(name: str) -> bool:
    return name.lower().endswith('.fb')


def _safe_rel(name: str, what: str) -> str:
    """a '/'-relative path from the image that stays inside its tree (the image is user input)."""
    n = name.replace('\\', '/')
    parts = n.split('/')
    if n.startswith('/') or any(p in ('..',) for p in parts) or ':' in n or not n.strip('/'):
        raise PrepareError('E_ISO_READ', f'{what}: unsafe path {name!r}', 'the image is damaged or not the game')
    return n


def identify(img: image.XdvdfsImage) -> dict:
    """the disc's identity (raises PrepareError when it is not a complete X-Men Legends disc)."""
    e = img.get(XBE_PATH)
    if e is None or e.is_dir:
        raise PrepareError('E_ISO_WRONG_GAME', 'no default.xbe on this disc: not an Xbox game disc',
                           'choose your X-Men Legends (Xbox) disc image', {'xbe': 'missing'})
    data = img.read_file(XBE_PATH)
    info = xbe.parse(data)
    xbe.check_xml1(info)
    missing = []
    z = img.get(ZIP_PATH)
    if z is None or z.is_dir or z.size == 0:
        missing.append(ZIP_PATH)
    if not img.files_under('sounds/zsds'):
        missing.append('sounds/zsds/')
    if not [f for f in img.files_under('movies/ntsc') if f.path.lower().endswith('.sfd')]:
        missing.append('movies/ntsc/*.sfd')
    if missing:
        raise PrepareError('E_ISO_INCOMPLETE', f'the disc lacks {", ".join(missing)}',
                           'this looks like a demo disc or an incomplete rip - dump the full disc again',
                           {'missing': missing})
    try:
        zf = zipfile.ZipFile(img.open_file(ZIP_PATH))
    except zipfile.BadZipFile as ex:
        raise PrepareError('E_ISO_READ', f'{ZIP_PATH} is not a readable zip ({ex})', 'the image is damaged')
    members = [(i.filename, i.file_size, i.CRC, i.compress_type) for i in zf.infolist()]
    zip_digest = digest(members)
    xbe_md5 = hashlib.md5(data).hexdigest()
    return {'format': img.format, 'partition': img.partition, 'image': img.path.as_posix(), 'image_size': img.size,
            'xbe': info, 'xbe_md5': xbe_md5, 'zip_digest': zip_digest, 'zip_members': len(members),
            'listing_digest': digest(img.listing()), 'disc_id': f'{xbe_md5[:12]}{zip_digest[:8]}'}


def stage_key(ident: dict) -> str:
    """the P1 cache key: the stage version + the disc content (never the image path or its layout)."""
    return digest({'stage': STAGE, 'version': VERSION, 'xbe_md5': ident['xbe_md5'],
                   'zip_digest': ident['zip_digest'], 'listing_digest': ident['listing_digest']})


def find_published(cache) -> list:
    """published P1 directories of this stage version under a cache."""
    out = []
    for d in sorted(Path(cache).glob(f'*/{STAGE}')):
        st = read_stage(d)
        if st and st.get('stage') == STAGE and st.get('version') == VERSION:
            out.append(d)
    return out


def has_movies(stage: dict) -> bool:
    """does a published P1 hold xbox/movies/ntsc? (stage.json 'movies'; P1 v1 directories made before the option
    always copied them)"""
    return bool((stage or {}).get('movies', True))


def run(iso, cache, *, log=print, cancel=None, progress=None, force=False, movies=True) -> dict:
    """P1 for a disc image into a cache; reuses the published output while its key matches (and adds the movie
    files to it when movies=True and it was prepared without them). movies=False leaves the 648 MB of movies out
    (a --no-movies build reads movies.json instead). Returns {'dir': Path, 'stage': stage.json dict, 'cached': bool}."""
    t0 = time.time()
    with image.open_image(iso) as img:
        ident = identify(img)
        key = stage_key(ident)
        final = Path(cache) / ident['disc_id'] / STAGE
        st = read_stage(final)
        if st and st.get('key') == key and not force:
            if movies and not has_movies(st):
                st = add_movies(img, final, st, log=log, cancel=cancel, progress=progress)
            log(f'[prepare] disc: cached ({final}; {ident["xbe"]["title"]}, {ident["format"]}; '
                f'movies {"copied" if has_movies(st) else "not copied"})')
            return {'dir': final, 'stage': st, 'cached': True}
        partial = final.with_name(STAGE + '.partial')
        rmtree(partial)
        partial.mkdir(parents=True)
        log(f'[prepare] disc: reading {img.path.name} ({ident["format"]}, "{ident["xbe"]["title"]}" '
            f'{ident["xbe"]["title_id_hex"]}) -> {final}')
        counts, timings, conflicts = extract(img, partial, log=log, cancel=cancel, progress=progress, movies=movies)
    stage = {'stage': STAGE, 'version': VERSION, 'key': key, 'disc_id': ident['disc_id'], 'identity': ident,
             'movies': bool(movies), 'counts': counts, 'timings': timings, 'conflicts': conflicts,
             'seconds': round(time.time() - t0, 1)}
    stage = publish(partial, final, stage)
    log(f'[prepare] disc: done in {stage["seconds"]}s: {counts}')
    return {'dir': final, 'stage': stage, 'cached': False}


def extract(img: image.XdvdfsImage, dst: Path, *, log=print, cancel=None, progress=None, movies=True):
    """write xbox/ (movies/ntsc only with movies=True), assets/, loose/ (+ manifest) and movies.json into dst.
    Returns (counts, timings, conflicts)."""
    dst = Path(dst)
    counts = {'xbox_files': 0, 'xbox_bytes': 0, 'assets_files': 0, 'assets_bytes': 0, 'bundles': 0,
              'bundle_entries': 0, 'loose_files': 0, 'loose_bytes': 0, 'conflicting_duplicates': 0,
              'identical_duplicates': 0}
    timings = {}
    disc_files = [img.get(XBE_PATH)] + [e for d in DISC_DIRS if movies or d != MOVIE_DIR
                                        for e in img.files_under(d)]
    zf = zipfile.ZipFile(img.open_file(ZIP_PATH))
    infos = zf.infolist()
    total = len(disc_files) + len(infos)
    done = 0

    def tick():
        nonlocal done
        done += 1
        check_cancel(cancel)
        if progress is not None:
            progress(done, total, 'files')

    # ---- disc files -> xbox/
    t = time.time()
    for e in disc_files:
        rel = _safe_rel(e.path, 'disc file')
        counts['xbox_bytes'] += img.copy_file(e.path, dst / XBOX / rel)
        counts['xbox_files'] += 1
        tick()
    timings['xbox'] = round(time.time() - t, 1)

    # ---- zip members -> assets/ (the bundles are unpacked below, in fb_unpack's order)
    t = time.time()
    bundles = []
    try:
        for info in infos:
            name = _safe_rel(info.filename, ZIP_PATH)
            if info.is_dir():
                (dst / ASSETS / name).mkdir(parents=True, exist_ok=True)
                tick()
                continue
            if _is_bundle(name):
                bundles.append(info)
                continue
            p = dst / ASSETS / name
            p.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(p, 'wb') as o:
                shutil.copyfileobj(src, o, 8 << 20)
            counts['assets_files'] += 1
            counts['assets_bytes'] += info.file_size
            tick()
        timings['assets'] = round(time.time() - t, 1)

        # ---- bundles -> loose/ (never written as .fb files)
        t = time.time()
        manifest, first, conflicts = {}, {}, []
        for info in sorted(bundles, key=lambda i: fb.bundle_order_key(i.filename)):
            rel = info.filename
            data = zf.read(info)
            manifest[rel] = []
            counts['bundles'] += 1
            try:
                recs = list(fb.entries(data, rel))
            except fb.BundleError as ex:
                raise PrepareError('E_ISO_READ', str(ex), 'the image is damaged')
            for raw_name, kind, body in recs:
                name = raw_name.lstrip('/').lower()          # fb_unpack.py's manifest name
                manifest[rel].append([name, kind])
                counts['bundle_entries'] += 1
                h = hashlib.md5(body).hexdigest()
                if name in first:
                    if first[name] != h:
                        conflicts.append([name, rel])
                        counts['conflicting_duplicates'] += 1
                    else:
                        counts['identical_duplicates'] += 1
                    continue
                first[name] = h
                p = dst / LOOSE / _safe_rel(name, rel)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, 'wb') as o:
                    o.write(body)
                counts['loose_files'] += 1
                counts['loose_bytes'] += len(body)
            tick()
    except (zipfile.BadZipFile, zlib.error, EOFError) as ex:     # bad CRC / deflate data / truncated member
        raise PrepareError('E_ISO_READ', f'{ZIP_PATH}: {ex}', 'the image is damaged - dump it again')
    (dst / LOOSE).mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, indent=1).replace('\n', NEWLINE)
    (dst / LOOSE / MANIFEST).write_bytes(text.encode('ascii'))
    timings['loose'] = round(time.time() - t, 1)

    # ---- movies.json (the NTSC movies' facts, for providers that must work without the files)
    t = time.time()
    (dst / MOVIES_JSON).write_text(json.dumps(movie_index(img), indent=1), encoding='utf-8')
    timings['movies_json'] = round(time.time() - t, 1)
    return counts, timings, conflicts


def movie_index(img: image.XdvdfsImage) -> list:
    """[{name, path, size, dirs, duration, info}] of the disc's movies/ntsc/**.sfd, read from the image
    (media.sofdec_info_bytes over each movie's first 2 MB: the parser media's providers use on the files, so
    info equals media._sofdec_info of the copied file). path = below xbox/, spelled as on the disc."""
    from .. import media
    rows = []
    for e in img.files_under(MOVIE_DIR):
        if not e.path.lower().endswith('.sfd'):
            continue
        with img.open_file(e.path) as f:
            head = f.read(media.SOFDEC_LIMIT)
        info = media.sofdec_info_bytes(head, e.size)
        c0 = (info.get('adx') or {}).get('c0') or {}
        parts = e.path.split('/')
        rows.append({'name': parts[-1].rsplit('.', 1)[0].lower(), 'path': e.path, 'size': e.size,
                     'dirs': [x.lower() for x in parts[2:-1]],
                     'duration': round(c0['samples'] / c0['rate'], 2) if c0.get('rate') and c0.get('samples') else None,
                     'info': info})
    return rows


def add_movies(img: image.XdvdfsImage, final: Path, stage: dict, *, log=print, cancel=None, progress=None) -> dict:
    """copy movies/ntsc into a published P1 directory that was prepared without them (a movies build after a
    --no-movies one): into a sibling '.partial' tree first, then renamed into xbox/, then stage.json says so."""
    t0 = time.time()
    files = img.files_under(MOVIE_DIR)
    part = Path(final) / (XBOX + '.movies.partial')
    rmtree(part)
    log(f'[prepare] disc: adding the {len(files)} movie files to {final}')
    n = 0
    for i, e in enumerate(files):
        check_cancel(cancel)
        n += img.copy_file(e.path, part / _safe_rel(e.path, 'disc file'))
        if progress is not None:
            progress(i + 1, len(files), 'files')
    top = files[0].path.split('/')[0] if files else 'movies'
    dest = Path(final) / XBOX / top
    rmtree(dest)                                  # a half-added tree from an interrupted run
    rename(part / top, dest)
    rmtree(part)
    st = dict(stage, movies=True)
    st['counts'] = dict(st.get('counts') or {}, movie_files=len(files), movie_bytes=n)
    st['timings'] = dict(st.get('timings') or {}, add_movies=round(time.time() - t0, 1))
    tmp = Path(final) / 'stage.json.tmp'
    tmp.write_text(json.dumps(st, indent=1), encoding='utf-8')
    os.replace(tmp, Path(final) / 'stage.json')
    return st


def expected_one_sided():
    """files of today's hand-made trees P1 deliberately does not produce, by rule (prepare_equiv explains them)."""
    return {
        'xml1_xbox': [
            (lambda r: r.lower() == ZIP_PATH, 'z/assetsfb.zip itself: P1 reads it in place into assets/ + loose/'),
            (lambda r: r.lower().startswith('movies/pal/'), 'PAL movies: never installed (XML2 PC plays NTSC only)'),
            (lambda r: r.lower().startswith('media/'), 'dashboard effect binaries: never read'),
            (lambda r: r.lower() in ('optionsimage.xpr', 'alchemy.ini', 'build.ini', 'sounds/badaudio.wav'),
             'Xbox-only settings / art / the fallback wav: never read (XML2 ships its own)'),
        ],
        'xml1_assets': [
            (lambda r: _is_bundle(r), '.fb bundle: unpacked into loose/ straight from the zip, never written'),
        ],
        'xml1_loose': [],
    }
