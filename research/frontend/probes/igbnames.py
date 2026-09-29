"""igbnames.py <igb>... : list length-prefixed string fields (u32 padded_len, NUL-terminated, zero padded to 4)."""
import re, struct, sys, collections
for p in sys.argv[1:]:
    d = open(p, 'rb').read()
    seen = collections.Counter()
    info = {}
    for m in re.finditer(rb'[A-Za-z0-9_\-. \\/:]{2,}\x00', d):
        s = m.start()
        if s < 4:
            continue
        (plen,) = struct.unpack_from('<I', d, s - 4)
        body = m.group(0)[:-1]
        if plen % 4 or not len(body) + 1 <= plen <= len(body) + 4:
            continue
        n = body.decode()
        seen[n] += 1
        info[n] = plen
    print('==', p, len(d))
    for n in sorted(seen):
        if n.startswith('ig') or n in ('Actor', 'Application', 'Attribute', 'Audio', 'Bootstrap', 'Current', 'Default',
                                        'DriverData', 'Frame', 'Handles', 'Image', 'ImageData', 'ImageObject', 'Level',
                                        'MetaData', 'NonTracked', 'Physics', 'RenderList', 'Static', 'String', 'System',
                                        'Temporary', 'Texture', 'Vertex', 'VertexArrayData', 'VertexData', 'Video',
                                        'World') or n.startswith('User'):
            continue
        print(f'  {n:40} x{seen[n]} field={info[n]}')
