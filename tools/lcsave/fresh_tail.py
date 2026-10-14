"""Transient native-transfer provenance; never a durable LC field.

State zero is not referenced by any native entity list. Its definition handle
keeps a string alive through native string-table compaction; its payload marks
the string as transfer metadata. A normal zone capture clears this sentinel.
"""
from . import oldsave
from .keys import key_hash

MAGIC = b'LCFRESH1'


def text(zone, prefix, numbering):
    return '|'.join(('LCFT1', key_hash(zone.lower()), prefix['old'].hex(),
                     numbering['sha1'], ','.join(str(p) for p in prefix['placements'])))


def metadata(native, binds):
    """Validate host-authenticated append intent against this peer's actual map.

The receiver need not have the host's optional prefix sidecar. As with native
entity state, the source history comes from the host; the destination map and
all entity associations are checked locally. No zero-slot heuristic is used.
"""
    out = {}
    for record in native['zones']:
        sentinel = record['states'][0]
        if sentinel['payload'] != MAGIC:
            continue
        def bad():
            raise ValueError('invalid native fresh-tail provenance')
        if (not record['state_count'] or sentinel['inst_name'] or sentinel['flags_a'] or
                sentinel['flags_b'] or any(sentinel['position'])):
            bad()
        zone = oldsave.zone_string(native['zone_strings'], record['name_handle']).lower()
        fields = oldsave.zone_string(native['zone_strings'], sentinel['def_name']).split('|')
        if len(fields) != 5 or fields[:2] != ['LCFT1', key_hash(zone)]:
            bad()
        numbering = binds.zone_numbering(zone)
        if not numbering or numbering['problems'] or fields[3] != numbering['sha1']:
            bad()
        if any(len(s) != 40 or any(c not in '0123456789abcdef' for c in s) for s in fields[2:4]):
            bad()
        source = bytes.fromhex(fields[2])
        if source == bytes(20) or fields[2] == fields[3]:
            bad()
        parts = fields[4].split(',')
        if not 0 < len(parts) < len(numbering['numbered']) or len(parts) > len(record['ordinal_map']):
            bad()
        if any(not p or len(p) > 10 or any(c not in '0123456789' for c in p) or
               (len(p) > 1 and p[0] == '0') for p in parts):
            bad()
        placements = [int(p) for p in parts]
        if len(set(placements)) != len(placements) or any(p > 0xffffffff for p in placements):
            bad()
        if any(record['ordinal_map'][len(placements):]) or zone in out:
            bad()
        entities = []
        for k, idx in enumerate(record['ordinal_map'][:len(placements)]):
            if not idx:
                continue
            state = record['states'][idx]
            dn = oldsave.zone_string(native['zone_strings'], state['def_name'])
            inn = oldsave.zone_string(native['zone_strings'], state['inst_name'])
            nd, ni, pi = numbering['numbered'][k]
            if (key_hash(dn), key_hash(inn)) != (key_hash(nd), key_hash(ni)):
                bad()
            entities.append(dict(ordinal=k+1, placement_index=pi, source_placement_index=placements[k],
                                 definition_name=dn, instance_name=inn))
        out[zone] = dict(zone=zone, time_stamp=record['time_stamp'], capture_flags=2,
                         placement_sha1=bytes.fromhex(fields[3]), source_placement_sha1=source,
                         conversation_digest=bytes(32), entities=entities,
                         fresh_entities=[dict(ordinal=k+1, placement_index=pi, definition_name=dn, instance_name=inn)
                                         for k, (dn, inn, pi) in enumerate(numbering['numbered']) if k >= len(placements)])
    return out
