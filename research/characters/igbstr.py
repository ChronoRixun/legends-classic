"""igbstr.py <file.igb> [...] : print the non-meta strings of IGB files (object names, bones, anims)."""
import re, sys
META = re.compile(r'^(ig[A-Z]\w*|VertexArrayData|ImageData|VertexData|system|Bootstrap|Default|Current|NonTracked|System|Static|MetaData|String|Fast|List|Temporary|Vertex|RenderList|Texture|Application|World|Actor|Level|Frame|Physics|DriverData|Clut|Audio|Video|Handles|Image|ImageObject|Attribute|Node|User\d+)$')


def names(path, minlen=4):
    d = open(path, 'rb').read()
    out = []
    for m in re.finditer(rb'[\x20-\x7e]{%d,}\x00' % minlen, d):
        s = m.group()[:-1].decode()
        if META.match(s):
            continue
        out.append(s)
    return out


if __name__ == '__main__':
    for p in sys.argv[1:]:
        n = names(p)
        print(f'== {p} ({len(n)} strings)')
        print(sorted(set(n)))
