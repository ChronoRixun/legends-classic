"""xml1builder.inputs - the two inputs, identified and checked (BUILDER_DESIGN.md 1.1, 1.2).

The disc image: read in place by xml1build.prepare (image.py: Redump XGD1/2/3 or XISO by content; xbe.py: the
certificate; disc.identify: title ID 0x4156001E, the required files, the digests). Errors keep prepare's codes, with
one exception that follows the launcher's fake builder: a folder is E_ISO_NOT_XBOX with detail.detected = "folder"
(prepare says E_ISO_FOLDER). A dump that is not in data/known_dumps.json builds with W_ISO_UNKNOWN_DUMP.

The XML2 install: XMen2.exe present and a PE32 image at 0x400000 (E_XML2_NOT_FOUND), its md5 in data/known_xml2.json
(E_XML2_UNKNOWN_EXE; --allow-unknown-exe turns it into W_XML2_UNKNOWN_EXE: xml2-fix guards every patch site against
the retail bytes and leaves another build alone, so the port would silently lose New Game, forced parties, the XP
curve and the limits), English data (E_XML2_LANGUAGE). Its base files - every file but the xml2-fix proxy - are
compared by name and size with the retail reference (data/xml2_retail_files.json.gz) for info; the build hashes
them anyway and compares the hashes (W_XML2_MODIFIED, recorded in the stamp)."""
from __future__ import annotations

import fnmatch
import gzip
import hashlib
import json
import os
import struct
from pathlib import Path

from . import resources as R
from .errors import BuilderError
from .events import mask

PROXY = ('dinput.dll', 'mods', 'xml2-fix.*')             # = xml1build.common.PROXY_PATTERNS
RETAIL_FILES = 'xml2_retail_files.json.gz'
MODIFIED_LIMIT = 50


def _digest(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def known_dumps() -> list:
    return (R.load_json('known_dumps.json', {}) or {}).get('dumps', [])


def known_exes() -> dict:
    return (R.load_json('known_xml2.json', {}) or {}).get('exes', {})


_RETAIL = None


def retail_files() -> dict:
    """{lower rel: [size, sha1]} of the retail English XML2 install (the reference), {} when not packaged."""
    global _RETAIL
    if _RETAIL is None:
        try:
            with gzip.open(R.data_path(RETAIL_FILES), 'rt', encoding='utf-8') as fh:
                _RETAIL = json.load(fh).get('files', {})
        except (OSError, ValueError):
            _RETAIL = {}
    return _RETAIL


# ------------------------------------------------------------------------------------------------ the disc image
def identify_iso(path) -> dict:
    """info.iso of a disc image, or BuilderError (exit 3)."""
    return identify(path)[1]


def identify(path):
    """(P1's identity, info.iso) of a disc image, or BuilderError (exit 3). Reads default.xbe and the zip's central
    directory, nothing else."""
    from xml1build.prepare import PrepareError, disc as P1, image
    p = Path(path)
    if p.is_dir():
        raise BuilderError('E_ISO_NOT_XBOX', 'This is a folder, not a disc image.',
                           'Choose the disc image file (.iso) of your X-Men Legends Xbox disc.',
                           {'detected': 'folder', 'path': mask(p)})
    try:
        with image.open_image(p) as img:
            ident = P1.identify(img)
    except PrepareError as e:
        code = 'E_ISO_NOT_XBOX' if e.code == 'E_ISO_FOLDER' else e.code
        detail = dict(e.detail)
        if e.code == 'E_ISO_FOLDER':
            detail['detected'] = 'folder'
        if code == 'E_ISO_NOT_FOUND':
            detail.setdefault('path', mask(p))
        raise BuilderError(code, _sentence(e.msg), _sentence(e.hint) if e.hint else None, detail) from e
    except OSError as e:
        raise BuilderError('E_IO', f'The disc image could not be read: {e.strerror or e}.', None,
                           {'path': mask(p), 'errno': e.errno}) from e
    return ident, describe_disc(ident, p)


def describe_disc(ident: dict, path=None) -> dict:
    """info.iso / the stamp's disc from P1's identity."""
    known = next((d for d in known_dumps() if d.get('xbe_md5') == ident.get('xbe_md5')
                  and d.get('zip_digest') in (None, ident.get('zip_digest'))), None)
    xbe = ident.get('xbe') or {}
    return {'path': mask(path) if path else None, 'format': ident.get('format'), 'title': xbe.get('title'),
            'title_id': xbe.get('title_id_hex'), 'xbe_md5': ident.get('xbe_md5'), 'zip_digest': ident.get('zip_digest'),
            'known': bool(known), 'dump': (known or {}).get('id', ''), 'movies': True,
            'digest': disc_digest(ident), 'disc_id': ident.get('disc_id'), 'image_size': ident.get('image_size')}


def disc_digest(ident: dict) -> str:
    """the disc's content identity (not the image file's path or layout)."""
    return _digest({'xbe_md5': ident.get('xbe_md5'), 'zip_digest': ident.get('zip_digest'),
                    'listing_digest': ident.get('listing_digest')})


def _sentence(text):
    text = str(text or '').strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if text.endswith(('.', '!', '?')) else text + '.'


def deep_check_disc(path) -> list:
    """--deep: every member of z/assetsfb.zip read and CRC-checked in place (~10 s). -> [problem, ...]."""
    import zipfile
    from xml1build.prepare import disc as P1, image
    problems = []
    with image.open_image(path) as img:
        with zipfile.ZipFile(img.open_file(P1.ZIP_PATH)) as z:
            bad = z.testzip()
            if bad:
                problems.append(f'{P1.ZIP_PATH}: {bad} fails its CRC')
    return problems


# ------------------------------------------------------------------------------------------------ the XML2 install
def is_proxy(name: str) -> bool:
    n = name.lower()
    return any(fnmatch.fnmatchcase(n, p) for p in PROXY)


def base_listing(folder) -> dict:
    """{actual rel: (size, mtime_ns)} of the XML2 install's base files (everything but the proxy at the root)."""
    folder = str(folder)
    found = {}
    for dirpath, dirnames, filenames in os.walk(folder):
        rel_dir = os.path.relpath(dirpath, folder).replace(os.sep, '/')
        if rel_dir == '.':
            rel_dir = ''
            dirnames[:] = [d for d in dirnames if not is_proxy(d)]
            filenames = [f for f in filenames if not is_proxy(f)]
        for f in filenames:
            rel = f'{rel_dir}/{f}' if rel_dir else f
            try:
                st = os.stat(os.path.join(dirpath, f))
            except OSError:
                continue
            found[rel] = (st.st_size, st.st_mtime_ns)
    return found


def base_digest(listing: dict) -> str:
    """the install's identity for the stamp: names + sizes (a copy of the install keeps it; mtimes may not)."""
    return _digest(sorted((rel.lower(), v[0]) for rel, v in listing.items()))


def _pe_image_base(data: bytes):
    if data[:2] != b'MZ' or len(data) < 0x40:
        return None
    off = struct.unpack_from('<I', data, 0x3C)[0]
    if data[off:off + 4] != b'PE\0\0' or off + 0x38 > len(data):
        return None
    magic = struct.unpack_from('<H', data, off + 0x18)[0]
    if magic != 0x10B:                                    # PE32
        return None
    return struct.unpack_from('<I', data, off + 0x34)[0]


def compare_retail(listing: dict, hashes: dict | None = None) -> dict:
    """the install against the retail reference: {changed, missing, added} (lists of lower rels). With hashes
    ({rel: sha1}) the content is compared, else only the sizes."""
    ref = retail_files()
    if not ref:
        return {'reference': False, 'changed': [], 'missing': [], 'added': []}
    have = {rel.lower(): (rel, v) for rel, v in listing.items()}
    changed, added = [], []
    for low, (rel, (size, _)) in sorted(have.items()):
        r = ref.get(low)
        if r is None:
            added.append(rel)
        elif r[0] != size or (hashes is not None and rel in hashes and hashes[rel] != r[1]):
            changed.append(rel)
    missing = sorted(low for low in ref if low not in have)
    return {'reference': True, 'changed': changed, 'missing': missing, 'added': added}


def modified_list(cmp: dict) -> list:
    return ([f'changed: {r}' for r in cmp['changed']] + [f'missing: {r}' for r in cmp['missing']]
            + [f'added: {r}' for r in cmp['added']])


def check_xml2(folder, *, allow_unknown=False, warn=None, listing=None) -> dict:
    """info.xml2 (and the stamp's xml2 without the path) or BuilderError (exit 3). warn(code, msg, detail)."""
    folder = Path(folder)
    exe = folder / 'XMen2.exe'
    if not folder.is_dir() or not exe.is_file():
        raise BuilderError('E_XML2_NOT_FOUND', 'X-Men Legends II was not found in this folder (no XMen2.exe).', None,
                           {'path': mask(folder)})
    try:
        data = exe.read_bytes()
    except OSError as e:
        raise BuilderError('E_IO', f'XMen2.exe could not be read: {e.strerror or e}.', None, {'path': mask(exe)}) from e
    if _pe_image_base(data) != 0x400000:
        raise BuilderError('E_XML2_NOT_FOUND', 'XMen2.exe in this folder is not the X-Men Legends II program.', None,
                           {'path': mask(folder), 'reason': 'not a PE32 image at 0x400000'})
    md5 = hashlib.md5(data).hexdigest()
    exe_info = known_exes().get(md5)
    if exe_info is None:
        detail = {'exe_md5': md5, 'size': len(data)}
        if not allow_unknown:
            raise BuilderError('E_XML2_UNKNOWN_EXE', 'This version of X-Men Legends II (XMen2.exe) is not supported.',
                               None, detail)
        if warn:
            warn('W_XML2_UNKNOWN_EXE', 'This XMen2.exe is not a known retail build (--allow-unknown-exe): xml2-fix '
                                       'may leave the port\'s engine fixes off.', detail)
    data_dir = next((c for c in folder.iterdir() if c.name.lower() == 'data' and c.is_dir()), None)
    sounds = next((c for c in folder.iterdir() if c.name.lower() == 'sounds' and c.is_dir()), None)
    english = data_dir is not None and any(c.name.lower() == 'herostat.engb' for c in data_dir.iterdir()) and \
        sounds is not None and any(c.name.lower() == 'eng' and c.is_dir() for c in sounds.iterdir())
    if not english:
        raise BuilderError('E_XML2_LANGUAGE', 'This X-Men Legends II install has no English data '
                           '(Data/herostat.engb, Sounds/eng).', None, {'path': mask(folder)})
    listing = base_listing(folder) if listing is None else listing
    cmp = compare_retail(listing)
    modified = modified_list(cmp)
    return {'path': mask(folder), 'exe_known': exe_info is not None, 'exe_md5': md5,
            'exe': (exe_info or {}).get('id', ''), 'language': 'ENG', 'base_files': len(listing),
            'base_bytes': sum(v[0] for v in listing.values()), 'base_digest': base_digest(listing),
            'reference': cmp['reference'], 'modified': modified[:MODIFIED_LIMIT], 'modified_count': len(modified)}
