"""
ZTRK track bytecode (sound sequences), grammar taken from XMen2.exe's interpreter (identical instruction stream in
the XML1 xbe, see cmpcode.py):
  blob = "ZTRK" event*            (track start pointer = entry+8 + 4, XMen2.exe 0x592d9d)
  event byte b: code = b & 7, type = b & 0xF8                              (0x593610)
    prefix bytes after b by code: 0:0 1:1 2:4 3:1 4:2 5:5 6:4 7:8          (jump table 0x59382c)
      (codes 3..5 carry a 1-byte delta-time, 6..7 a 4-byte delta-time; 1,2,4,5,7 also a value)
    type 0xF8: extended event (0x5936e0) -- not used by any XML1 / XML2 track
    args by type: 0x00:2 (note, velocity)  0x08:1 (note)  0x10:2 (controller cmd, value)
                  0x18:2 (end / loop control)  0x30:4  0x20/0x28/0x38/0x40:0  >0x40: stop   (table 0x593878)
  controller 0x10 cmd 4 = select sound by 1-byte index into the bank's sound table (0x592ef8 -> 0x5956c0),
  cmd 5 = index into table T6 (0x595700), cmd 0 = volume, cmd 1 = pan.
"""
PREFIX = {0: 0, 1: 1, 2: 4, 3: 1, 4: 2, 5: 5, 6: 4, 7: 8}
ARGS = {0x00: 2, 0x08: 1, 0x10: 2, 0x18: 2, 0x30: 4, 0x20: 0, 0x28: 0, 0x38: 0, 0x40: 0}


class ZtrkError(Exception):
    pass


def parse(blob):
    """Return list of events (offset, b, prefix_bytes, type, args_bytes). Raises on grammar violations."""
    if blob[:4] != b'ZTRK':
        raise ZtrkError('no magic')
    p = 4
    out = []
    end = len(blob.rstrip(b'\0')) if blob.rstrip(b'\0') else len(blob)
    while p < end:
        b = blob[p]
        code, typ = b & 7, b & 0xF8
        if typ == 0xF8:
            raise ZtrkError('extended event at %d' % p)
        if typ not in ARGS:
            raise ZtrkError('unknown type %#x at %d' % (typ, p))
        pre = blob[p + 1:p + 1 + PREFIX[code]]
        a0 = p + 1 + PREFIX[code]
        args = blob[a0:a0 + ARGS[typ]]
        if a0 + ARGS[typ] > len(blob):
            raise ZtrkError('truncated at %d' % p)
        out.append((p, b, pre, typ, args))
        p = a0 + ARGS[typ]
    return out


def sound_refs(blob):
    """Offsets (into blob) of every 1-byte sound index (controller 0x10, cmd 4)."""
    refs = []
    for off, b, pre, typ, args in parse(blob):
        if typ == 0x10 and args[0] == 4 and args[1] != 0xFF:
            refs.append(off + 1 + len(pre) + 1)
    return refs


def remap(blob, fn):
    """Return blob with every sound index i replaced by fn(i) (must stay < 255)."""
    out = bytearray(blob)
    for o in sound_refs(blob):
        n = fn(out[o])
        if not 0 <= n < 0xFF:
            raise ZtrkError('sound index %d not encodable' % n)
        out[o] = n
    return bytes(out)


if __name__ == '__main__':
    import sys, collections
    from xml1build.lib import zsnd
    stats = collections.Counter()
    if not sys.argv[1:]:          # research/sound/ztrk.py passes the developer default
        sys.exit('usage: python -m xml1build.lib.ztrk <Xbox sounds/zsds folder> [...]')
    for root in sys.argv[1:]:
        for p in zsnd.iter_banks(root):
            b = zsnd.load(p, strict=False)
            for i, t in enumerate(b.tracks):
                blob = b.ztrk[i] if i < len(b.ztrk) else b''
                try:
                    ev = parse(blob)
                except ZtrkError as e:
                    stats['bad'] += 1
                    print('BAD', p, i, e, blob[:40].hex(' '))
                    continue
                stats['tracks'] += 1
                for off, bb, pre, typ, args in ev:
                    stats['type%#04x' % typ] += 1
                    stats['code%d' % (bb & 7)] += 1
                    if typ == 0x10:
                        stats['ctl_cmd%d' % args[0]] += 1
                refs = sound_refs(blob)
                if any(blob[o] >= len(b.sounds) for o in refs):
                    stats['sound_ref_out_of_range'] += 1
                if ev[-1][3] != 0x18:
                    stats['not_ending_with_0x18'] += 1
                if (t.raw[2], t.raw[3]) != (0xff, 0xff):
                    stats['entry_initial_refs'] += 1
    print(dict(stats))
