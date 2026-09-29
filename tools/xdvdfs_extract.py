"""Extract the game partition of an Xbox (Redump-style) disc image."""
import os, struct, sys

SECTOR = 2048
PARTITION_OFFSETS = (0x18300000, 0x0FD90000, 0x02080000, 0)

def find_partition(f):
    for base in PARTITION_OFFSETS:
        f.seek(base + 0x10000)
        if f.read(20) == b'MICROSOFT*XBOX*MEDIA':
            return base
    raise SystemExit('no XDVDFS partition found')

def walk(f, base, sector, size, out, rel=''):
    f.seek(base + sector * SECTOR)
    data = f.read(size)
    stack = [0]
    seen = set()
    while stack:
        off = stack.pop()
        if off in seen or off + 14 > len(data):
            continue
        seen.add(off)
        left, right, start, length, attrs, nlen = struct.unpack_from('<HHIIBB', data, off)
        if left == 0xFFFF:
            continue
        name = data[off + 14:off + 14 + nlen].decode('latin-1')
        if left: stack.append(left * 4)
        if right: stack.append(right * 4)
        path = os.path.join(rel, name)
        if attrs & 0x10:
            os.makedirs(os.path.join(out, path), exist_ok=True)
            if length:
                walk(f, base, start, length, out, path)
        else:
            dst = os.path.join(out, path)
            os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
            f.seek(base + start * SECTOR)
            with open(dst, 'wb') as o:
                remaining = length
                while remaining:
                    chunk = f.read(min(remaining, 1 << 20))
                    o.write(chunk)
                    remaining -= len(chunk)

def main(iso, out):
    with open(iso, 'rb') as f:
        base = find_partition(f)
        f.seek(base + 0x10000 + 20)
        root_sector, root_size = struct.unpack('<II', f.read(8))
        os.makedirs(out, exist_ok=True)
        walk(f, base, root_sector, root_size, out)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
