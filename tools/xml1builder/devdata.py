"""xml1builder.devdata - (developers) regenerate the builder's reference data in tools/xml1builder/data/.
Hashes and sizes only - never game content (BUILDER_DESIGN.md 5.1: "hashes of known-good inputs").

    python -m xml1builder.devdata xml2 --xml2 "<XML2 folder>" [--id retail-en]
        known_xml2.json (XMen2.exe md5 -> build id) + xml2_retail_files.json.gz (every base file: size, sha1)
    python -m xml1builder.devdata dump --cache DIR [--disc-id ID] [--id xml1-world-v1] [--title NAME]
        adds / replaces a known_dumps.json entry from a prepared disc's identity (P1 stage.json)"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

from . import resources as R


def _write(name, data):
    p = R.data_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
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
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == '__main__':
    main()
