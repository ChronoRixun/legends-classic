"""Unpack XML1 .fb bundles (name[0x80], type[0x40], u32 size, data) into a loose-file tree."""
import collections, glob, hashlib, json, os, struct, sys

def entries(path):
    d = open(path, 'rb').read()
    off = 0
    while off + 0xC4 <= len(d):
        name = d[off:off + 0x80].split(b'\0')[0].decode('latin-1')
        kind = d[off + 0x80:off + 0xC0].split(b'\0')[0].decode('latin-1')
        size, = struct.unpack_from('<I', d, off + 0xC0)
        data = d[off + 0xC4:off + 0xC4 + size]
        if not name or len(data) != size:
            raise ValueError(f'{path}: bad entry at {off:#x}')
        yield name, kind, data
        off += 0xC4 + size

def main(src, out):
    manifest = {}
    kinds = collections.Counter()
    conflicts = []
    hashes = {}
    for fb in sorted(glob.glob(os.path.join(src, '**', '*.fb'), recursive=True)):
        rel = os.path.relpath(fb, src).replace(os.sep, '/')
        manifest[rel] = []
        for name, kind, data in entries(fb):
            name = name.lstrip('/').lower()
            manifest[rel].append([name, kind])
            kinds[kind] += 1
            h = hashlib.md5(data).hexdigest()
            if name in hashes:
                if hashes[name] != h:
                    conflicts.append((name, rel))
                continue
            hashes[name] = h
            dst = os.path.join(out, name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(data)
    json.dump(manifest, open(os.path.join(out, '_fb_manifest.json'), 'w'), indent=1)
    print(len(manifest), 'bundles,', len(hashes), 'unique files,', len(conflicts), 'conflicting duplicates')
    print(kinds.most_common())
    for c in conflicts[:10]:
        print('conflict', c)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
