"""
ZSND sound bank parser / writer for Raven's X-Men Legends (Xbox "ZSNDXBOX") and
X-Men Legends II PC ("ZSNDPC  ").

Layout (all little endian), established by parsing every bank of both games and by the
XML2 PC loader at XMen2.exe 0x594e50 (relocates the table pointers below):

  0x00 char[8]  magic          "ZSNDPC  " / "ZSNDXBOX"
  0x08 u32      file_size      PC: exact file size (1 exception, boss4_m). XBOX: rounded up to 0x800.
  0x0C u32      header_size    end of all metadata (tables + ZTRK blobs); PC: first sample data offset
  0x10 7 x {u32 count, u32 keys_off, u32 entries_off}
        T0 sounds   (entry 24 bytes on both platforms)
        T1 samples  (entry 24 PC / 28 XBOX)
        T2 files    (entry 76 PC / 84 XBOX)   ("sample file" = one blob of audio data)
        T3 unused   (engine: array of u32 pointers to variable structs; count is 0 in all 562 banks)
        T4 tracks   (entry 16 bytes -> "ZTRK" bytecode blob)
        T5 unused   (engine does not relocate it)
        T6 unused   (engine: array of u32 pointers; count 0 everywhere)
  0x64  data: for each table, keys = count x {u32 hash, u32 entry_index} sorted by hash
        (engine does a binary search @0x595720 / 0x595780), then entries.

Keys: T0/T4 keys = zhash.elf_hash(name) = PJW/ELF hash over toupper(chars) of the '\\'->'/' name
(XMen2.exe 0x590280 / 0x5924e0); random variants are separate T0 entries keyed
elf_hash('/***RANDOM***/<n>', seed=elf_hash(name)). T1/T2 keys are opaque hashes of build-machine names (not
used by lookups; preserved verbatim). Every entry has exactly one key; keys may repeat in XML2 PC banks.

T0 sound entry (24):   u16 sample_index, u16 flags(0x1000), u8 volume(0x7f), u8 0, u8 b6 (0xff/0x32/...), u8 0,
                       u8 0, u8 0x7f, u8 0, u8 0x7f, 10 x u8 0 ; runtime writes bank id at +0x16.
                       Identical layout on both platforms.
T1 sample entry:       u16 file_index, u8 flags, u8 0, u32 sample_rate, zeros (PC 16 bytes, XBOX 20)
                       flags: 0x01 loop (ac_loop, rain_loop...), 0x02 stereo (engine 0x5950a8 / 0x595ac0),
                       0x04 8-bit (engine; never set), 0x20 (set on "_c" combat-music samples in both games)
                       runtime writes bank id at +0x16 (PC)
T2 file entry PC:      u32 offset, u32 size, u32 format, char name[64] (".wav")
                       format 0x6a = headerless IMA ADPCM (all 9016 XML2 files); for .zsm banks any other value
                       is treated as raw 16-bit PCM (0x595137); .zss streams are always decoded as IMA (0x595aa0)
T2 file entry XBOX:    u32 offset (2 KB aligned), u32 size, u32 format (1 = xbadpcm mono, 3 = xbadpcm stereo music),
                       u32 0, u32 0, char name[64] (".xbadpcm")
T4 track entry (16):   u8 volume 0x7f, u8 0, u8 initial sound index (0xff none), u8 T6 index (0xff none),
                       u32 0, u32 ztrk_offset (absolute; engine plays from +4, after "ZTRK"), u16 0,
                       u16 bank id (runtime, +0xE). Bytecode grammar: ztrk.py.
"""
import struct, os

MAGIC_PC = b'ZSNDPC  '
MAGIC_XBOX = b'ZSNDXBOX'
ESIZE = {MAGIC_PC: (24, 24, 76, 4, 16, 0, 4), MAGIC_XBOX: (24, 28, 84, 4, 16, 0, 4)}
TNAMES = ['sounds', 'samples', 'files', 't3', 'tracks', 't5', 't6']


class ZsndError(Exception):
    pass


class Entry:
    __slots__ = ('hashes', 'raw', 'index')

    def __init__(self, raw, index):
        self.raw = raw
        self.index = index
        self.hashes = []

    def u16(self, off):
        return struct.unpack_from('<H', self.raw, off)[0]

    def u32(self, off):
        return struct.unpack_from('<I', self.raw, off)[0]


class Bank:
    def __init__(self, data, path=None, strict=True):
        self.path = path
        self.data = data
        self.problems = []
        if len(data) < 0x64:
            raise ZsndError('too small')
        self.magic = data[:8]
        if self.magic not in ESIZE:
            raise ZsndError('bad magic %r' % self.magic)
        self.platform = 'pc' if self.magic == MAGIC_PC else 'xbox'
        self.file_size, self.header_size = struct.unpack_from('<II', data, 8)
        self.tabs = [struct.unpack_from('<III', data, 0x10 + 12 * i) for i in range(7)]
        es = ESIZE[self.magic]
        self.tables = []
        spans = []  # (start, end, what) for overlap check of metadata
        for ti, (cnt, ko, vo) in enumerate(self.tabs):
            ents = []
            if cnt:
                if ti in (3, 5, 6):
                    self._bad('table %s non-empty (%d)' % (TNAMES[ti], cnt))
                    self.tables.append(ents)
                    continue
                sz = es[ti]
                spans.append((ko, ko + 8 * cnt, TNAMES[ti] + '.keys'))
                spans.append((vo, vo + sz * cnt, TNAMES[ti] + '.entries'))
                if vo + sz * cnt > len(data):
                    self._bad('%s entries past EOF' % TNAMES[ti])
                for i in range(cnt):
                    ents.append(Entry(data[vo + i * sz: vo + (i + 1) * sz], i))
                prev = -1
                seen = [0] * cnt
                for i in range(cnt):
                    h, idx = struct.unpack_from('<II', data, ko + 8 * i)
                    if h < prev:
                        self._bad('%s keys not sorted at %d' % (TNAMES[ti], i))
                    elif h == prev:
                        self._bad('%s duplicate key %08x at %d' % (TNAMES[ti], h, i), soft=True)
                    prev = h
                    if idx >= cnt:
                        self._bad('%s key %d -> bad index %d' % (TNAMES[ti], i, idx))
                        continue
                    ents[idx].hashes.append(h)
                    seen[idx] += 1
                for i, s in enumerate(seen):
                    if s != 1:
                        self._bad('%s entry %d referenced by %d keys' % (TNAMES[ti], i, s))
            self.tables.append(ents)
        self.sounds, self.samples, self.files, _, self.tracks, _, _ = self.tables
        # metadata layout: contiguous from 0x64, no overlaps
        spans.sort()
        pos = 0x64
        for a, b, w in spans:
            if a < pos:
                self._bad('metadata overlap at %s (%#x < %#x)' % (w, a, pos))
            elif a != pos:
                self._bad('metadata gap before %s (%#x..%#x)' % (w, pos, a))
            pos = max(pos, b)
        self.tables_end = pos
        # tracks: ZTRK blobs between tables_end and header_size
        self.ztrk = []
        if self.tracks:
            offs = [t.u32(8) for t in self.tracks]
            order = sorted(range(len(offs)), key=lambda i: offs[i])
            bounds = [offs[i] for i in order] + [self.header_size]
            if bounds[0] != self.tables_end:
                self._bad('first ZTRK at %#x, tables end %#x' % (bounds[0], self.tables_end))
            blobs = [None] * len(offs)
            for k, i in enumerate(order):
                blob = data[bounds[k]:bounds[k + 1]]
                if not blob.startswith(b'ZTRK'):
                    self._bad('track %d blob @%#x lacks ZTRK' % (i, bounds[k]))
                blobs[i] = blob
            self.ztrk = blobs
        elif self.header_size != self.tables_end:
            self._bad('header_size %#x != tables end %#x' % (self.header_size, self.tables_end))
        # cross references
        for s in self.sounds:
            si = s.u16(0)
            if si >= len(self.samples) and si != 0xffff:
                self._bad('sound %d -> sample %d out of range' % (s.index, si))
        for s in self.samples:
            fi = s.u16(0)
            if fi >= len(self.files) and fi != 0xffff:
                self._bad('sample %d -> file %d out of range' % (s.index, fi))
        # file data ranges
        fr = []
        for f in self.files:
            off, size = f.u32(0), f.u32(4)
            if off < self.header_size:
                self._bad('file %d data @%#x inside header (%#x)' % (f.index, off, self.header_size))
            if off + size > len(data):
                self._bad('file %d data %#x+%#x past EOF %#x' % (f.index, off, size, len(data)))
            fr.append((off, off + size, f.index))
        fr.sort()
        for (a0, a1, ai), (b0, b1, bi) in zip(fr, fr[1:]):
            if b0 < a1:
                self._bad('file data overlap %d/%d' % (ai, bi))
        self.data_ranges = fr
        # size field
        if self.platform == 'pc':
            if self.file_size != len(data):
                self._bad('pc file_size %d != actual %d' % (self.file_size, len(data)), soft=True)
        else:
            if not (len(data) <= self.file_size < len(data) + 0x800 or self.file_size == len(data)):
                self._bad('xbox file_size %d vs actual %d' % (self.file_size, len(data)), soft=True)
        if strict and [p for p in self.problems if not p.startswith('~')]:
            raise ZsndError('; '.join(self.problems))

    def _bad(self, msg, soft=False):
        self.problems.append(('~' if soft else '') + msg)

    # ---- convenience views
    def file_name(self, f):
        nm = f.raw[-64:]
        return nm.split(b'\0')[0].decode('latin1')

    def file_format(self, f):
        return f.u32(8)

    def file_bytes(self, f):
        off, size = f.u32(0), f.u32(4)
        return self.data[off:off + size]

    def sample_info(self, s):
        return {'file': s.u16(0), 'flags': s.raw[2], 'rate': s.u32(4)}

    def summary(self):
        return {'platform': self.platform, 'sounds': len(self.sounds), 'samples': len(self.samples),
                'files': len(self.files), 'tracks': len(self.tracks),
                'sound_keys': sum(len(s.hashes) for s in self.sounds),
                'data_bytes': sum(b - a for a, b, _ in self.data_ranges)}


def load(path, strict=True):
    with open(path, 'rb') as fh:
        return Bank(fh.read(), path, strict)


def iter_banks(root):
    for dp, dn, fn in os.walk(root):
        for f in sorted(fn):
            if f.lower().endswith(('.zss', '.zsm')):
                yield os.path.join(dp, f).replace('\\', '/')


if __name__ == '__main__':
    import sys, collections
    roots = sys.argv[1:]          # bank folders (research/sound/zsnd.py passes the developer defaults)
    if not roots:
        sys.exit('usage: python -m xml1build.lib.zsnd <bank folder> [...]')
    for root in roots:
        tot = collections.Counter()
        nbad = 0
        soft = collections.Counter()
        paths = sorted(iter_banks(root))
        for p in paths:
            try:
                b = load(p, strict=False)
            except ZsndError as e:
                print('FAIL', p, e)
                nbad += 1
                continue
            hard = [x for x in b.problems if not x.startswith('~')]
            if hard:
                nbad += 1
                print('BAD ', p, hard[:5])
            for x in b.problems:
                if x.startswith('~'):
                    soft[x.split(' ')[0] + ' ' + x.split(' ')[1]] += 1
                    if b.platform == 'pc':
                        print('note', p, x)
            for k, v in b.summary().items():
                if k != 'platform':
                    tot[k] += v
            tot['banks'] += 1
        print(root, dict(tot), 'bad banks:', nbad, 'soft notes:', dict(soft))
