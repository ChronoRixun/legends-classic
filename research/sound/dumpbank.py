"""Human-readable dump of a bank: sound keys -> sample -> file name, flags, rate, size; tracks with bytecode."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, json, zsnd
from zhash import elf_hash

def names_db():
    """hash -> name from resolved reference JSONs (both games) if present."""
    db = {}
    for g in ('xml1', 'xml2'):
        try:
            for n in json.load(open(_REPO + '/research/sound/soundrefs_%s.json' % g)):
                db[elf_hash(n)] = n
        except FileNotFoundError:
            pass
    return db

def dump(path, db=None, out=sys.stdout):
    b = zsnd.load(path, strict=False)
    db = db if db is not None else names_db()
    print('%s  %s  sounds=%d samples=%d files=%d tracks=%d hdr=%#x' % (path, b.platform, len(b.sounds), len(b.samples), len(b.files), len(b.tracks), b.header_size), file=out)
    for s in b.sounds:
        si = s.u16(0)
        smp = b.samples[si] if si < len(b.samples) else None
        f = b.files[smp.u16(0)] if smp is not None and smp.u16(0) < len(b.files) else None
        nm = [db.get(h, '?') for h in s.hashes]
        print('  snd %3d keys=%s name=%s -> smp %d flags=%#x rate=%d -> file %s fmt=%#x size=%d  vol=%d b6=%d' % (
            s.index, ','.join('%08x' % h for h in s.hashes), '|'.join(nm), si, smp.raw[2] if smp else -1, smp.u32(4) if smp else 0,
            b.file_name(f) if f else None, f.u32(8) if f else 0, f.u32(4) if f else 0, s.raw[4], s.raw[6]), file=out)
    for i, t in enumerate(b.tracks):
        print('  trk %3d keys=%s name=%s raw=%s ztrk=%s' % (i, ','.join('%08x' % h for h in t.hashes), '|'.join(db.get(h, '?') for h in t.hashes), t.raw.hex(), b.ztrk[i].hex(' ')), file=out)

if __name__ == '__main__':
    for p in sys.argv[1:]:
        dump(p)
