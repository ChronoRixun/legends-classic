"""Independent check of adpcm.xbox_decode against ffmpeg: wrap Xbox ADPCM data in a WAVE_FORMAT_XBOX_ADPCM (0x69)
RIFF, decode with ffmpeg, compare sample-by-sample (ffmpeg's IMA-WAV decoder emits the block header sample as an
extra sample, 65 per block, so every 65th ffmpeg sample is dropped before comparing)."""
import struct, subprocess, sys, os, array, tempfile
import zsnd, adpcm

def wrap(data, ch, rate):
    fmt = struct.pack('<HHIIHHHH', 0x69, ch, rate, rate * 36 * ch // 64, 36 * ch, 4, 2, 64)
    body = b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(data)) + data
    return b'RIFF' + struct.pack('<I', 4 + len(body)) + b'WAVE' + body

def check(path, idx, tmp):
    b = zsnd.load(path)
    f = b.files[idx]
    s = next(x for x in b.samples if x.u16(0) == idx)
    ch = 2 if s.raw[2] & 2 else 1
    rate = s.u32(4)
    data = b.file_bytes(f)
    wp = os.path.join(tmp, 'x.wav')
    open(wp, 'wb').write(wrap(data, ch, rate))
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wp, '-f', 's16le', '-acodec', 'pcm_s16le', '-'],
                         capture_output=True).stdout
    ff = array.array('h', raw)
    ffc = [ff[c::ch] for c in range(ch)]
    mine, st = adpcm.xbox_decode(data, ch)
    n65 = len(ffc[0])
    # drop header samples (index 0 of each 65-sample block)
    ffd = ffc if len(ffc[0]) == len(mine[0]) else [array.array("h", [x for k, x in enumerate(c) if k % 65 != 0]) for c in ffc]
    cmp = adpcm.compare(mine, ffd)
    print('%s file %d (%s) ch=%d rate=%d: mine=%d ffmpeg=%d(65/blk)->%d  %s  stats=%s' % (
        os.path.basename(path), idx, b.file_name(f), ch, rate, len(mine[0]), n65, len(ffd[0]), cmp, adpcm.pcm_stats(mine)))

if __name__ == '__main__':
    tmp = tempfile.mkdtemp()
    for spec in sys.argv[1:]:
        p, i = spec.rsplit(':', 1)
        check(p, int(i), tmp)
