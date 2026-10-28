"""Builder attestations for append-only resident numbering; no save-container changes.

Generate after content conversion, against the stable release build and (for a later beta) the previous beta:
    python -m lcsave.zonecompat plan     --previous STABLE [--previous PREVIOUS_BETA] CURRENT_BUILD
    python -m lcsave.zonecompat generate --previous STABLE [--previous PREVIOUS_BETA] CURRENT_BUILD \
        --ledger-out tools/lcsave/data/zone_prefixes.json
(`PREVIOUS_BUILD CURRENT_BUILD` alone is `generate` with one previous build; tools/lcsave/README.md.)
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


def zone_hash(zone):
    """Use the same case normalization as Binds.zone_numbering before hashing."""
    return bytes.fromhex(key_hash(zone.lower()))


def prefix_digest(entries):
    return hashlib.sha256(json.dumps(entries, ensure_ascii=True, separators=(',', ':')).encode('ascii')).digest()


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
    old_root, new_root = xmlb.decode(previous), xmlb.decode(current)
    old, placements = resident_prefix(old_root)
    new, new_placements = resident_prefix(new_root)
    if not old or len(new) <= len(old) or new[:len(old)] != old:
        return None
    digest = prefix_digest(old)
    def placed(root):
        return [(g, i) for g in root.iter('entinst') for i in g.iter('inst')]
    old_placed, new_placed = placed(old_root), placed(new_root)
    tail_placements = set(new_placements[len(old):])
    old_residents = set(placements)
    remaining = {(bytes.fromhex(key_hash(g.get('type') or '')), bytes.fromhex(key_hash(i.get('name') or '')))
                 for p, (g, i) in enumerate(new_placed) if p not in tail_placements}
    fresh, ambiguous, promoted_old = set(), set(), set()
    for p in new_placements[len(old):]:
        group, inst = new_placed[p]
        current_pair = (bytes.fromhex(key_hash(group.get('type') or '')),bytes.fromhex(key_hash(inst.get('name') or '')))
        if current_pair in remaining: ambiguous.add(current_pair)
        for old_index, (old_group, old_inst) in enumerate(old_placed):
            if old_index in old_residents: continue
            if _canonical(inst) != _canonical(old_inst): continue
            if sorted((k,v) for k,v in group.attrib.items() if k != 'type') != sorted((k,v) for k,v in old_group.attrib.items() if k != 'type'):
                return None
            promoted_old.add(old_index)
            pair = (bytes.fromhex(key_hash(old_group.get('type') or '')), bytes.fromhex(key_hash(old_inst.get('name') or '')))
            (ambiguous if pair in remaining else fresh).add(pair)
    # An append must not smuggle a world-setting, untouched smart-placement or
    # unrelated definition edit through an unchanged numbered prefix.
    def placed_value(group, inst): return [sorted(group.attrib.items()), _canonical(inst)]
    if [placed_value(g,i) for p,(g,i) in enumerate(old_placed) if p not in promoted_old] != [
            placed_value(g,i) for p,(g,i) in enumerate(new_placed) if p not in tail_placements]:
        return None
    def frame(root):
        return [root.tag, sorted(root.attrib.items()), [_canonical(e) for e in root if e.tag not in ('entity','entinst')]]
    if frame(old_root) != frame(new_root): return None
    tail_types = {new_placed[p][0].get('type') for p in tail_placements}
    old_tail_types = {old_placed[p][0].get('type') for p in promoted_old}
    old_tail_types -= {g.get('type') for p,(g,_) in enumerate(old_placed) if p not in promoted_old}
    # Previously unused definitions may become a new tail; no old placed state names them.
    old_tail_types |= tail_types - {g.get('type') for g,_ in old_placed}
    old_all = {e.get('name'):_canonical(e) for e in old_root.iter('entity')}
    new_all = {e.get('name'):_canonical(e) for e in new_root.iter('entity')}
    for name in old_tail_types-tail_types:
        if name in new_all and new_all[name] != old_all[name]: return None
    old_defs = {n:e for n,e in old_all.items() if n not in old_tail_types}
    new_defs = {n:e for n,e in new_all.items() if n not in tail_types | old_tail_types}
    if old_defs != new_defs: return None
    return dict(zone=zone_hash(zone), old=hashlib.sha1(previous).digest(),
                current=hashlib.sha1(current).digest(), digest=digest, placements=placements,
                fresh_aliases=sorted(fresh-ambiguous), ambiguous_aliases=sorted(ambiguous))


# Definition attributes a saved zone record never depends on: the restore puts position, orientation, state flags
# and the class payload on the entity of the same ordinal, and none of these attributes change numbering (classname,
# smartent, monster_smartent, instantspawn, checkteam stay compared), the class or the payload's meaning.
#   xml1heaviness: XML1's lift class 4/5, read only by XML2 Fix gameplay rule 38 (LiftRule=xml1) and the Blob
#                  controller when a definition is parsed; the converted heaviness byte itself is unchanged.
EQUIVALENT_ATTRIBUTES = frozenset({'xml1heaviness'})


# Owner-reviewed definition-attribute edits a saved record does not depend on either, each bound to ONE zone, ONE
# definition and ONE attribute, and to the SHA-256 of that attribute's exact previous and current values (hashes only:
# no game text enters the repository). The same attribute changed anywhere else, or to any other value, still rejects.
#   astroid_m/visit1/asteroid2_1 shieldup actscript (beta 8, Magneto controller 9449620 / SPEC 106.2, reviewed and
#       allowed by the owner 2026-10-26): boss_phases removes SPEC 36's inserted invulnerability suffix from the action
#       entity's script when the Magneto controller (rule 40) owns that protection. shieldup keeps its ordinal,
#       placement, class and flags; its saved state means the same on both maps.
REVIEWED_CHANGES = frozenset({
    ('astroid_m/visit1/asteroid2_1', 'shieldup', 'actscript',
     '4aa338bd54cc744977583faddc92883121c2909fd8b88b7d974b80baa97fe36d',
     '0eb3e283e0714b83d87c6ec8fca5b1836b3c4a1347d4407e7d55a2f8189bb3f4'),
})


def value_sha256(value):
    """The reviewed-change hash of one attribute value (latin-1, as XMLB stores it)."""
    return hashlib.sha256(value.encode('latin-1')).hexdigest()


def _canonical_without(e, ignored, top=frozenset()):
    """_canonical without the `ignored` attributes (at every depth) and the `top` attributes (on `e` itself only)."""
    return [e.tag, sorted((k, v) for k, v in e.attrib.items() if k not in ignored and k not in top),
            [_canonical_without(c, ignored) for c in e]]


def _reviewed(zone, name, old, new, reviewed):
    """Attributes of definition `name` whose previous -> current values in `zone` are an owner-reviewed edit."""
    out = set()
    for z, definition, attribute, before, after in reviewed:
        if z != zone or definition != name: continue
        a, b = old.get(attribute), new.get(attribute)
        if a is not None and b is not None and value_sha256(a) == before and value_sha256(b) == after:
            out.add(attribute)
    return out


def attest_equivalent(zone, previous, current, ignored=EQUIVALENT_ATTRIBUTES, reviewed=None):
    """Return a full-length attestation (every numbered entity is prefix, no tail) when the two maps differ only in
    `ignored` definition attributes and in `reviewed` edits of this zone: same framing, same placements in order (group
    attributes and instances exact), same definition names, and every definition equal once the ignored attributes
    (and its reviewed edits) are removed. The saved record's numbered ordinals, placement indices and smart/dynamic
    names then mean exactly what they meant on `previous`. `reviewed` defaults to REVIEWED_CHANGES."""
    zone = zone.lower()
    reviewed = REVIEWED_CHANGES if reviewed is None else reviewed
    old_root, new_root = xmlb.decode(previous), xmlb.decode(current)
    old_num, old_problems = numbered_entities(old_root)
    new_num, new_problems = numbered_entities(new_root)
    if old_problems or new_problems or not new_num or old_num != new_num:
        return None
    def frame(root):
        return [root.tag, sorted(root.attrib.items()), [_canonical(e) for e in root if e.tag not in ('entity', 'entinst')]]
    if frame(old_root) != frame(new_root):
        return None
    def placed(root):
        return [[sorted(g.attrib.items()), _canonical(i)] for g in root.iter('entinst') for i in g.iter('inst')]
    if placed(old_root) != placed(new_root):
        return None
    def elements(root):
        out = {}
        for e in root.iter('entity'):
            if e.get('name') in out:
                raise BindError('zone-prefix.lcm: duplicate entity definition')
            out[e.get('name')] = e
        return out
    old_defs, new_defs = elements(old_root), elements(new_root)
    if set(old_defs) != set(new_defs):
        return None
    for name, old in old_defs.items():
        new = new_defs[name]
        top = frozenset(_reviewed(zone, name, old, new, reviewed))
        if _canonical_without(old, ignored, top) != _canonical_without(new, ignored, top):
            return None
    entries, placements = resident_prefix(new_root)
    # The runtime recomputes the digest from the current opened map, so bind the row to the current prefix.
    return dict(zone=zone_hash(zone), old=hashlib.sha1(previous).digest(), current=hashlib.sha1(current).digest(),
                digest=prefix_digest(entries), placements=placements, fresh_aliases=[], ambiguous_aliases=[])


def retarget(rows, zone, previous_sha1, current):
    """Rows that end at `previous_sha1` re-targeted to the `current` map, which attest_equivalent proved equivalent
    to the previous map: the numbered list, placements and names are unchanged, so each row's old placement indices
    and aliases stay valid; only the current hash and the current-prefix digest change."""
    out = []
    root = xmlb.decode(current)
    entries, _ = resident_prefix(root)
    for r in rows:
        if r['zone'] != zone_hash(zone) or r['current'] != previous_sha1:
            continue
        n = len(r['placements'])
        if n > len(entries):
            continue
        out.append(dict(r, current=hashlib.sha1(current).digest(), digest=prefix_digest(entries[:n])))
    return out


def encode(rows):
    rows = sorted(rows, key=lambda r: (r['zone'], r['old'], r['current']))
    if len(rows) > LIMIT:
        raise BindError('zone-prefix.lcm: invalid prefix count')
    body = bytearray()
    seen = set()
    for r in rows:
        key = (r['zone'], r['old'], r['current'])
        if key in seen or not 0 < len(r['placements']) <= LIMIT:
            raise BindError('zone-prefix.lcm: duplicate or invalid prefix')
        seen.add(key)
        if any(len(r[k]) != n for k,n in (('zone',32),('old',20),('current',20),('digest',32))):
            raise BindError('zone-prefix.lcm: invalid hash width')
        body += r['zone'] + r['old'] + r['current'] + r['digest']
        body += struct.pack('<I', len(r['placements']))
        body += struct.pack('<' + 'I' * len(r['placements']), *r['placements'])
        for field in ('fresh_aliases', 'ambiguous_aliases'):
            pairs = r.get(field, [])
            if len(pairs) > LIMIT or len(set(pairs)) != len(pairs):
                raise BindError('zone-prefix.lcm: invalid aliases')
            if any(len(a)!=32 or len(b)!=32 for a,b in pairs):
                raise BindError('zone-prefix.lcm: invalid alias hash width')
            body += struct.pack('<I', len(pairs))
            body += b''.join(a+b for a,b in pairs)
    return MAGIC + struct.pack('<IIII', 2, len(rows), 24 + len(body), zlib.crc32(body)) + body


def decode(raw):
    def bad(): raise BindError('zone-prefix.lcm: invalid framing or entry')
    if len(raw) < 24 or raw[:8] != MAGIC: bad()
    version, count, size, crc = struct.unpack_from('<IIII', raw, 8)
    if version != 2 or count > LIMIT or size != len(raw) or crc != zlib.crc32(raw[24:]): bad()
    rows, seen, off = [], set(), 24
    for _ in range(count):
        if off + 108 > len(raw): bad()
        r = dict(zone=raw[off:off+32], old=raw[off+32:off+52], current=raw[off+52:off+72], digest=raw[off+72:off+104])
        n, = struct.unpack_from('<I', raw, off + 104)
        off += 108
        if not 0 < n <= LIMIT or off + 4*n > len(raw): bad()
        r['placements'] = list(struct.unpack_from('<' + 'I'*n, raw, off))
        off += 4*n
        for field in ('fresh_aliases', 'ambiguous_aliases'):
            if off+4 > len(raw): bad()
            count_pairs, = struct.unpack_from('<I', raw, off); off += 4
            if count_pairs > LIMIT or off+64*count_pairs > len(raw): bad()
            r[field] = [(raw[off+64*i:off+64*i+32],raw[off+64*i+32:off+64*i+64]) for i in range(count_pairs)]
            off += 64*count_pairs
            if len(set(r[field])) != count_pairs: bad()
        if set(r['fresh_aliases']) & set(r['ambiguous_aliases']): bad()
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
            if set(entry) != {'zone','old','current','digest','placements','fresh_aliases','ambiguous_aliases'}:
                raise BindError('zone-prefix.lcm: invalid release ledger fields')
            r = {k: (v if k == 'placements' else [(bytes.fromhex(a),bytes.fromhex(b)) for a,b in v]
                     if k.endswith('_aliases') else bytes.fromhex(v)) for k, v in entry.items()}
            key = (r['zone'], r['old'], r['current'])
            if key in rows and rows[key] != r:
                raise BindError('zone-prefix.lcm: conflicting historical attestation')
            rows[key] = r
    return encode(list(rows.values()))


def validate_current(build):
    """V39: each applicable release attestation agrees with the built resident prefix."""
    binds = Binds(build)
    rows = load(build)
    active = 0
    for zone in sorted(set(binds.zone_names) | set(binds.all_zone_files())):
        numbering = binds.zone_numbering(zone)
        if numbering is None: continue
        for row in rows:
            if row['zone'] != zone_hash(zone) or row['current'].hex() != numbering['sha1']:
                continue  # history may describe another release's current map
            entries, _ = resident_prefix(xmlb.decode(Path(numbering['path']).read_bytes()))
            n = len(row['placements'])
            digest = prefix_digest(entries[:n])
            if n > len(entries) or digest != row['digest']:
                raise BindError('zone-prefix.lcm: current resident prefix differs from attestation')
            active += 1
    return active


def equivalent(row, numbering):
    """A matched row covering every numbered entity at its own placement: the maps are save-equivalent."""
    return row['placements'] == [p for _, _, p in numbering['numbered']]


def match(rows, zone, old_hash, numbering):
    """Current full-file SHA1 binds the builder's prefix comparison to actual opened bytes."""
    for r in rows:
        if r['zone'] == zone_hash(zone) and r['old'] == old_hash:
            # A full-length row (no tail) is an equivalence attestation (attest_equivalent).
            if r['current'].hex() == numbering['sha1'] and len(r['placements']) <= len(numbering['numbered']):
                # Check the digest against the same opened bytes as the numbering,
                # not only the editable sidecar's CRC and whole-file hash claims.
                raw = Path(numbering['path']).read_bytes()
                if hashlib.sha1(raw).hexdigest() != numbering['sha1']:
                    return None
                try:
                    entries, _ = resident_prefix(xmlb.decode(raw))
                except BindError:
                    return None
                if prefix_digest(entries[:len(r['placements'])]) == r['digest']:
                    return r
    return None


def plan(previous, current):
    """-> (rows, accepted, rejected, retargeted) for the current build: its retained rows, append-only and equivalence
    attestations against `previous`, and the previous build's rows re-targeted through an equivalence (a save made on
    an older map that `previous` accepted through a prefix row keeps that acceptance on `current`). Writes nothing."""
    return plan_all([previous], current)[:4]


def plan_all(previous_builds, current):
    """plan() against several previous builds (the stable release AND the previous beta, say) into one row set.
    -> (rows, accepted, rejected, retargeted, per_build): accepted/rejected are the union over the builds, retargeted
    lists every re-targeted row's zone, per_build maps each previous build to its own (accepted, rejected,
    retargeted). A zone one build rejects can still be accepted against another. Writes nothing."""
    after = Binds(current)
    rows = {(r['zone'], r['old'], r['current']): r for r in load(current)}
    def put(row):
        key = (row['zone'], row['old'], row['current'])
        if key in rows and rows[key] != row:
            raise BindError('zone-prefix.lcm: conflicting historical attestation')
        rows[key] = row
    per_build = {}
    for previous in previous_builds:
        before = Binds(previous)
        history = load(previous)
        accepted, rejected, retargeted = [], [], []
        for zone in sorted(set(after.zone_names) | set(after.all_zone_files())):
            old, new = before.zone_file(zone), after.zone_file(zone)
            if old is None or new is None: continue
            old_raw, new_raw = Path(old).read_bytes(), Path(new).read_bytes()
            if old_raw == new_raw: continue
            try:
                row = attest(zone, old_raw, new_raw)
                equivalent = None if row else attest_equivalent(zone, old_raw, new_raw)
            except BindError:
                row = equivalent = None  # one unmodelled zone must not abort unrelated attestations
            if row is None and equivalent is None:
                rejected.append(zone)
                continue
            put(row or equivalent)
            accepted.append(zone)
            if equivalent:
                for r in retarget(history, zone, hashlib.sha1(old_raw).digest(), new_raw):
                    if r['old'] != r['current']:
                        put(r); retargeted.append(zone)
        per_build[str(previous)] = (accepted, rejected, retargeted)
    accepted = sorted({z for a, _, _ in per_build.values() for z in a})
    rejected = sorted({z for _, r, _ in per_build.values() for z in r} - set(accepted))
    retargeted = [z for _, _, t in per_build.values() for z in t]
    return list(rows.values()), accepted, rejected, retargeted, per_build


def _report(rows, accepted, rejected, retargeted, per_build):
    return dict(accepted=accepted, rejected=rejected, retargeted=len(retargeted), entries=len(rows),
                per_build={k: dict(accepted=len(a), rejected=r, retargeted=len(t)) for k, (a, r, t) in per_build.items()})


def generate(previous, current, *more):
    """Write CURRENT's sidecar from plan_all([previous, *more], current); -> the report dict."""
    rows, accepted, rejected, retargeted, per_build = plan_all([previous, *more], current)
    destination = Path(current) / REL
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = encode(rows)
    decode(raw)
    temporary = destination.with_suffix('.tmp')
    temporary.write_bytes(raw)
    os.replace(temporary, destination)
    return _report(rows, accepted, rejected, retargeted, per_build)


def ledger_json(rows):
    """The release ledger text (tools/lcsave/data/zone_prefixes.json): hashes and placement indices only, sorted as
    the sidecar is."""
    rows = sorted(rows, key=lambda r: (r['zone'], r['old'], r['current']))
    return json.dumps([{k: (v.hex() if isinstance(v, bytes) else [[a.hex(), b.hex()] for a, b in v]
                            if k.endswith('_aliases') else v) for k, v in r.items()} for r in rows], indent=2) + '\n'


def main(argv=None):
    """python -m lcsave.zonecompat plan|generate --previous BUILD [--previous BUILD ...] CURRENT [--ledger-out FILE];
    the original form `python -m lcsave.zonecompat PREVIOUS CURRENT [--ledger-out FILE]` is `generate`.
    plan writes nothing but the optional ledger; generate also writes CURRENT's Data/lcsave/zone-prefix.lcm."""
    import argparse
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='python -m lcsave.zonecompat', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    if argv and argv[0] in ('plan', 'generate'):
        mode = argv.pop(0)
        parser.add_argument('--previous', action='append', required=True,
                            help='a previous release build (repeat it: the stable release AND the previous beta)')
        parser.add_argument('current')
    else:
        mode = 'generate'
        parser.add_argument('previous_build', metavar='previous'); parser.add_argument('current')
    parser.add_argument('--ledger-out', help='write the verified hash-only release ledger')
    args = parser.parse_args(argv)
    previous = getattr(args, 'previous', None) or [args.previous_build]
    if mode == 'plan':
        result = plan_all(previous, args.current)
        rows = result[0]
        decode(encode(rows))  # the row set must fit and round-trip the sidecar format
        report = _report(*result)
    else:
        report = generate(previous[0], args.current, *previous[1:])
        rows = load(args.current)
    print(json.dumps(report, indent=2))
    if args.ledger_out:
        Path(args.ledger_out).write_text(ledger_json(rows), encoding='utf-8', newline='\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
