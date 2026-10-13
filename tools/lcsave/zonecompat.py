"""Builder attestations for append-only resident numbering; no save-container changes.

Generate after content conversion, against each supported previous release build:
    python -m lcsave.zonecompat PREVIOUS_BUILD CURRENT_BUILD
Only hashes and placement indices enter the sidecar. Never infer compatibility
from names in a save: those do not authenticate old definitions or positions.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import zlib
from pathlib import Path

import xmlb
from .binds import Binds, BindError, numbered_entities
from .keys import key_hash

REL = 'Data/lcsave/zone-prefix.lcm'
MAGIC = b'LCZPFX1\0'
LIMIT = 4096


def _canonical(e):
    return [e.tag, sorted(e.attrib.items()), [_canonical(c) for c in e]]


def resident_prefix(root):
    """Ordinal entries authenticate complete definitions, group attributes and instances."""
    numbered, problems = numbered_entities(root)
    definitions = {}
    for e in root.iter('entity'):
        if e.get('name') in definitions:
            raise BindError('zone-prefix.lcm: duplicate entity definition')
        definitions[e.get('name')] = e
    if problems:
        raise BindError('zone-prefix.lcm: unmodelled numbering')
    placements = []
    for group in root.iter('entinst'):
        for inst in group.iter('inst'):
            placements.append((group, inst))
    entries = []
    for definition, name, placement in numbered:
        group, inst = placements[placement]
        entries.append([_canonical(definitions[definition]), sorted(group.attrib.items()), _canonical(inst)])
    return entries, [p for _, _, p in numbered]


def attest(zone, previous, current):
    """Return a hash-bound attestation only when the entire old resident prefix survives."""
    old, placements = resident_prefix(xmlb.decode(previous))
    new, _ = resident_prefix(xmlb.decode(current))
    if not old or len(new) <= len(old) or new[:len(old)] != old:
        return None
    digest = hashlib.sha256(json.dumps(old, ensure_ascii=True, separators=(',', ':')).encode('ascii')).digest()
    return dict(zone=bytes.fromhex(key_hash(zone)), old=hashlib.sha1(previous).digest(),
                current=hashlib.sha1(current).digest(), digest=digest, placements=placements)


def encode(rows):
    rows = sorted(rows, key=lambda r: (r['zone'], r['old'], r['current']))
    body = bytearray()
    seen = set()
    for r in rows:
        key = (r['zone'], r['old'], r['current'])
        if key in seen or not 0 < len(r['placements']) <= LIMIT:
            raise BindError('zone-prefix.lcm: duplicate or invalid prefix')
        seen.add(key)
        body += r['zone'] + r['old'] + r['current'] + r['digest']
        body += struct.pack('<I', len(r['placements']))
        body += struct.pack('<' + 'I' * len(r['placements']), *r['placements'])
    return MAGIC + struct.pack('<IIII', 1, len(rows), 24 + len(body), zlib.crc32(body)) + body


def decode(raw):
    def bad(): raise BindError('zone-prefix.lcm: invalid framing or entry')
    if len(raw) < 24 or raw[:8] != MAGIC: bad()
    version, count, size, crc = struct.unpack_from('<IIII', raw, 8)
    if version != 1 or count > LIMIT or size != len(raw) or crc != zlib.crc32(raw[24:]): bad()
    rows, seen, off = [], set(), 24
    for _ in range(count):
        if off + 108 > len(raw): bad()
        r = dict(zone=raw[off:off+32], old=raw[off+32:off+52], current=raw[off+52:off+72], digest=raw[off+72:off+104])
        n, = struct.unpack_from('<I', raw, off + 104)
        off += 108
        if not 0 < n <= LIMIT or off + 4*n > len(raw): bad()
        r['placements'] = list(struct.unpack_from('<' + 'I'*n, raw, off))
        off += 4*n
        key = (r['zone'], r['old'], r['current'])
        if key in seen or len(set(r['placements'])) != n or r['old'] == r['current']: bad()
        seen.add(key); rows.append(r)
    if off != len(raw): bad()
    return rows


def load(build):
    p = Path(build) / REL
    return decode(p.read_bytes()) if p.exists() else []


def build_sidecar(build):
    """Retain prior attestations and add the release ledger (hashes/indices only)."""
    rows = {(r['zone'], r['old'], r['current']): r for r in load(build)}
    ledger = Path(__file__).with_name('data') / 'zone_prefixes.json'
    if ledger.exists():
        for entry in json.loads(ledger.read_text(encoding='utf-8')):
            r = {k: (bytes.fromhex(v) if k != 'placements' else v) for k, v in entry.items()}
            key = (r['zone'], r['old'], r['current'])
            if key in rows and rows[key] != r:
                raise BindError('zone-prefix.lcm: conflicting historical attestation')
            rows[key] = r
    return encode(list(rows.values()))


def validate_current(build):
    """V-TBD: each applicable release attestation agrees with the built resident prefix."""
    binds = Binds(build)
    rows = load(build)
    active = 0
    for zone in binds.all_zone_files():
        numbering = binds.zone_numbering(zone)
        for row in rows:
            if row['zone'] != bytes.fromhex(key_hash(zone)) or row['current'].hex() != numbering['sha1']:
                continue  # history may describe another release's current map
            entries, _ = resident_prefix(xmlb.decode(Path(numbering['path']).read_bytes()))
            n = len(row['placements'])
            digest = hashlib.sha256(json.dumps(entries[:n], ensure_ascii=True, separators=(',', ':')).encode('ascii')).digest()
            if n >= len(entries) or digest != row['digest']:
                raise BindError('zone-prefix.lcm: current resident prefix differs from attestation')
            active += 1
    return active


def match(rows, zone, old_hash, numbering):
    """Current full-file SHA1 binds the builder's prefix comparison to actual opened bytes."""
    for r in rows:
        if r['zone'] == bytes.fromhex(key_hash(zone)) and r['old'] == old_hash:
            if r['current'].hex() == numbering['sha1'] and len(r['placements']) < len(numbering['numbered']):
                return r
    return None


def generate(previous, current):
    before, after = Binds(previous), Binds(current)
    rows = {(r['zone'], r['old'], r['current']): r for r in load(current)}
    accepted, rejected = [], []
    for zone in after.all_zone_files():
        old, new = before.zone_file(zone), after.zone_file(zone)
        if old is None: continue
        old_raw, new_raw = Path(old).read_bytes(), Path(new).read_bytes()
        if old_raw == new_raw: continue
        row = attest(zone, old_raw, new_raw)
        if row is None:
            rejected.append(zone)
        else:
            key = (row['zone'], row['old'], row['current'])
            if key in rows and rows[key] != row:
                raise BindError('zone-prefix.lcm: conflicting historical attestation')
            rows[key] = row
            accepted.append(zone)
    destination = Path(current) / REL
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = encode(list(rows.values()))
    decode(raw)
    temporary = destination.with_suffix('.tmp')
    temporary.write_bytes(raw)
    os.replace(temporary, destination)
    return dict(accepted=accepted, rejected=rejected, entries=len(rows))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous'); parser.add_argument('current')
    parser.add_argument('--ledger-out', help='write the verified hash-only release ledger')
    args = parser.parse_args()
    print(json.dumps(generate(args.previous, args.current), indent=2))
    if args.ledger_out:
        rows = load(args.current)
        Path(args.ledger_out).write_text(json.dumps([{k: (v.hex() if isinstance(v,bytes) else v) for k,v in r.items()}
            for r in rows], indent=2)+'\n', encoding='utf-8')
