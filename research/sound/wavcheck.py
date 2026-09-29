"""Decode samples from banks (either platform) to WAV and print sanity stats: duration, peak, rms, clipped
samples, zero-crossing rate. Usage: wavcheck.py <bank> [max_files] [wav_out_dir]"""
import sys, os, zsnd, adpcm

def main(path, maxf=5, outdir=None):
    b = zsnd.load(path, strict=False)
    print('%s (%s): %d files' % (path, b.platform, len(b.files)))
    for f in b.files[:maxf]:
        s = next(x for x in b.samples if x.u16(0) == f.index)
        ch = 2 if s.raw[2] & 2 else 1
        rate = s.u32(4)
        data = b.file_bytes(f)
        if b.platform == 'xbox':
            pcm, st = adpcm.xbox_decode(data, ch)
            expect = len(data) // (36 * ch) * 64
        elif f.u32(8) == 0x6a:
            pcm = adpcm.pc_decode(data, ch)
            expect = len(data) * 2 // ch
        else:
            import array
            a = array.array('h', data)
            pcm = [a[c::ch] for c in range(ch)]
            expect = len(data) // (2 * ch)
        st = adpcm.pcm_stats(pcm)
        print('  %-30s ch=%d rate=%5d fmt=%#x bytes=%8d samples=%8d (expected %8d) dur=%7.3fs peak=%5d rms=%7.1f clipped=%d zcr=%.3f flags=%#x' % (
            b.file_name(f)[:30], ch, rate, f.u32(8), len(data), len(pcm[0]), expect, len(pcm[0]) / rate, st['peak'], st['rms'], st['clipped'], st['zcr'], s.raw[2]))
        if outdir:
            os.makedirs(outdir, exist_ok=True)
            adpcm.write_wav(os.path.join(outdir, '%s__%s.wav' % (os.path.basename(path).replace('.', '_'), b.file_name(f).rsplit('.', 1)[0])), pcm, rate)

if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 5, sys.argv[3] if len(sys.argv) > 3 else None)
