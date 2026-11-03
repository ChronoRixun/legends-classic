"""xml1builder.devdata - (developers) regenerate the builder's reference data in tools/xml1builder/data/.
Hashes and sizes only - never game content (BUILDER_DESIGN.md 5.1: "hashes of known-good inputs").

    python -m xml1builder.devdata xml2 --xml2 "<XML2 folder>" [--id retail-en]
        known_xml2.json (XMen2.exe md5 -> build id) + xml2_retail_files.json.gz (every base file: size, sha1)
    python -m xml1builder.devdata dump --cache DIR [--disc-id ID] [--id xml1-world-v1] [--title NAME]
        adds / replaces a known_dumps.json entry from a prepared disc's identity (P1 stage.json)
    python -m xml1builder.devdata folder-reference --iso IMAGE
        known_dump_files.json: consumed originals' sizes/SHA-256, only from an image whose whole-image
        SHA-256 is already trusted in known_dumps.json. Reads the image without extracting any game data."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path

from . import resources as R


def _write(name, data):
    p = R.data_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8', newline='\n')
    return p


def cmd_xml2(a):
    from .inputs import base_listing
    from .manifest import sha1_file
    root = Path(a.xml2)
    listing = base_listing(root)
    files = {}
    for rel in sorted(listing, key=str.lower):
        size, sha1 = sha1_file(root / rel)
        files[rel.lower()] = [size, sha1]
    exe = (root / 'XMen2.exe').read_bytes()
    md5 = hashlib.md5(exe).hexdigest()
    known = R.load_json('known_xml2.json', {}) or {}
    exes = known.setdefault('exes', {})
    exes[md5] = {'id': a.id, 'size': len(exe), 'note': a.note}
    known['format'] = 1
    _write('known_xml2.json', known)
    blob = json.dumps({'format': 1, 'id': a.id, 'exe_md5': md5, 'files': files}, separators=(',', ':'))
    p = R.data_path('xml2_retail_files.json.gz')
    with gzip.GzipFile(p, 'wb', mtime=0) as fh:            # reproducible bytes
        fh.write(blob.encode('utf-8'))
    print(f'{len(files)} base files, exe {md5} -> {p} ({p.stat().st_size} bytes)')


def cmd_dump(a):
    from xml1build.prepare import disc as P1, read_stage
    found = [d for d in P1.find_published(a.cache) if a.disc_id is None or d.parent.name == a.disc_id]
    if len(found) != 1:
        sys.exit(f'{len(found)} prepared discs in {a.cache}; pass --disc-id')
    ident = (read_stage(found[0]) or {}).get('identity') or {}
    entry = {'id': a.id, 'title': a.title, 'title_id': (ident.get('xbe') or {}).get('title_id_hex'),
             'xbe_md5': ident.get('xbe_md5'), 'zip_digest': ident.get('zip_digest'),
             'listing_digest': ident.get('listing_digest'), 'zip_members': ident.get('zip_members'),
             'images': [{'format': ident.get('format'), 'size': ident.get('image_size')}]}
    known = R.load_json('known_dumps.json', {}) or {}
    dumps = [d for d in known.get('dumps', []) if d.get('id') != a.id]
    dumps.append(entry)
    _write('known_dumps.json', {'format': 1, 'dumps': dumps})
    print(json.dumps(entry, indent=1))


def folder_reference(path, known):
    """Hashes only, from a whole-image-trusted dump; XBE/ZIP-directory fingerprints alone are insufficient."""
    from xml1build.prepare import disc, folder, image
    p = Path(path)
    with image.XdvdfsImage(folder.open_readonly(p)) as img:
        before = folder._signature(os.fstat(img.fh.fileno()))
        candidates = [(d, i) for d in known for i in d.get('images', [])
                      if i.get('format') == img.format and i.get('size') == img.size and i.get('sha256')]
        if not candidates:
            raise ValueError('No trusted whole-image SHA-256 for this format/size in known_dumps.json')
        img.fh.seek(0)
        sha256 = hashlib.file_digest(img.fh, 'sha256').hexdigest()
        match = next((d for d, i in candidates if i['sha256'] == sha256), None)
        if match is None:
            raise ValueError('The image does not match a trusted whole-image SHA-256')
        ident = disc.identify(img)
        if any(ident.get(k) != match.get(k) for k in ('xbe_md5', 'zip_digest', 'listing_digest')):
            raise ValueError('Trusted image fingerprints disagree with known_dumps.json')
        files = {}
        for e in sorted(img.entries.values(), key=lambda e: e.path.lower()):
            rel = e.path.lower()
            if not e.is_dir and folder.consumed(rel):
                with img.open_file(e.path) as fh:
                    files[rel] = [e.size, hashlib.file_digest(fh, 'sha256').hexdigest()]
        img.fh.seek(0)
        after_hash = hashlib.file_digest(img.fh, 'sha256').hexdigest()
        if after_hash != sha256 or folder._signature(os.fstat(img.fh.fileno())) != before \
                or folder._signature(p.stat()) != before:
            raise ValueError('The image changed during reference generation')
        return {'id': match['id'], 'image_sha256': sha256, 'files': files}


def cmd_folder_reference(a):
    from xml1build.prepare.folder import REFERENCE_FILE
    try:
        entry = folder_reference(a.iso, (R.load_json('known_dumps.json', {}) or {}).get('dumps', []))
    except ValueError as e:
        sys.exit(str(e))
    old = (R.load_json(REFERENCE_FILE, {}) or {}).get('dumps', [])
    dumps = [d for d in old if d.get('id') != entry['id']] + [entry]
    _write(REFERENCE_FILE, {'format': 1, 'dumps': sorted(dumps, key=lambda d: d['id'])})
    print(f'{len(entry["files"])} verified original-file hashes -> {REFERENCE_FILE}')


def main(argv=None):
    R.setup()
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    x = sub.add_parser('xml2')
    x.add_argument('--xml2', required=True)
    x.add_argument('--id', default='retail-en')
    x.add_argument('--note', default='X-Men Legends II PC retail (English), 2005-09-08 build')
    x.set_defaults(fn=cmd_xml2)
    d = sub.add_parser('dump')
    d.add_argument('--cache', required=True)
    d.add_argument('--disc-id', dest='disc_id')
    d.add_argument('--id', default='xml1-world-v1')
    d.add_argument('--title', default='X-Men Legends (World) (Redump)')
    d.set_defaults(fn=cmd_dump)
    f = sub.add_parser('folder-reference')
    f.add_argument('--iso', required=True)
    f.set_defaults(fn=cmd_folder_reference)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == '__main__':
    main()
