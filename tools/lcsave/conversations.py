"""Native heard marks: four consumption lanes per alphabetically ranked conversation file.

The lanes count consumed run-once starts, not line ids (engine 0x45c56e / 0x45c679).
A stable file identity and lane carry the native semantics across package reorderings.
Historical tables contain hashes only; unknown provenance drops marks with a ledger note.
"""
import os
import hashlib
import struct
import xmlb
from .keys import key_hash


def zone_bits(build, zone):
    path = os.path.join(build, 'Packages', 'generated', 'maps', *zone.lower().split('/')) + '.pkgb'
    if not os.path.isfile(path):
        raise ValueError('conversation mapping: zone package missing')
    root = xmlb.decode(open(path, 'rb').read())
    files = set()
    for node in root.iter():
        attrs = {k.lower(): v for k, v in node.attrib.items()}
        name = attrs.get('filename', '').replace('\\', '/').lower()
        if name.startswith('conversations/'):
            if node.tag.lower() != 'xml':
                raise ValueError('conversation mapping: unsupported package resource')
            for ext in ('.engb', '.xmlb', '.eng', '.xml'):
                if name.endswith(ext): name = name[:-len(ext)]; break
            files.add(name[len('conversations/'):])
    if len(files) > 32:
        raise ValueError('conversation mapping: more than 32 loaded files')
    return [key_hash(name, str(lane)) for name in sorted(files) for lane in range(4)]


def build_tables(build, zones):
    return {key_hash(zone): zone_bits(build, zone) for zone in sorted(zones)
            if os.path.isfile(os.path.join(build, 'Packages', 'generated', 'maps', *zone.lower().split('/')) + '.pkgb')}


def package_digest(zone_hash, bits):
    """Versioned zone provenance: the exact native file/lane ranking, independent of dialogue bytes."""
    raw = b'LCCONV2\0' + bytes.fromhex(zone_hash) + struct.pack('<I', len(bits))
    raw += b''.join(bytes.fromhex(identity) for identity in bits)
    return hashlib.sha256(raw).hexdigest()


def zone_digest(build, zone):
    return package_digest(key_hash(zone), zone_bits(build, zone))


def current_tables(build, zones):
    return {(package_digest(zone, bits), zone): bits for zone, bits in build_tables(build, zones).items()}


def historical_tables(model):
    out = {}
    for era in list(model['eras'].values()) + model.get('conversation_snapshots', []):
        digest = era.get('conversation_digest')
        tables = era.get('conversation_bits', {})
        if tables == 'same': tables = model['reference']['conversation_bits']
        for zone, bits in tables.items():
            for provenance in (digest, package_digest(zone, bits)):
                key = (provenance, zone)
                if key in out and out[key] != bits:
                    raise ValueError('conversation mapping: conflicting eras for one digest and zone')
                out[key] = bits
    return out


def remap(words, source, target, zone, notes):
    if len(words) != 5: raise ValueError('conversation mapping: expected five words')
    if len(set(source)) != len(source) or len(set(target)) != len(target):
        raise ValueError('conversation mapping: duplicate identity')
    positions = {identity: bit for bit, identity in enumerate(target)}
    out = [0] * 5
    for bit in range(160):
        if not words[bit // 32] & (1 << (bit % 32)): continue
        if bit >= len(source):
            notes.append(f'zone {zone}: conversation bit {bit}: historical identity unknown: heard mark dropped')
            continue
        identity = source[bit]
        new = positions.get(identity)
        if new is None:
            notes.append(f'zone {zone}: conversation identity {identity}: absent in current package: heard mark dropped')
        else:
            out[new // 32] |= 1 << (new % 32)
    if out != list(words) and any(out):
        notes.append(f'zone {zone}: conversation identities remapped to current package')
    return out
