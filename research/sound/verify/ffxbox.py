"""Decode an XML1 Xbox sample with ffmpeg's decoders (default for tag 0x69, and forced adpcm_ima_xbox) and compare
with models A/B/C from blockcheck.py."""
import struct, subprocess, sys, os, array, tempfile
from blockcheck import bank, xbox_mono

xb = bank(sys.argv[1])
h = int(sys.argv[2], 16)
fl, rate, data, nm = xb[h]
fmt = struct.pack('<HHIIHHHH', 0x69, 1, rate, rate * 36 // 64, 36, 4, 2, 64)
body = b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(data)) + data
wav = b'RIFF' + struct.pack('<I', 4 + len(body)) + b'WAVE' + body
tmp = tempfile.mkdtemp()
wp = os.path.join(tmp, 'x.wav')
open(wp, 'wb').write(wav)
for forced in (None, 'adpcm_ima_xbox', 'adpcm_ima_wav'):
    cmd = ['ffmpeg', '-v', 'error', '-y']
    if forced:
        cmd += ['-c:a', forced]
    cmd += ['-i', wp, '-f', 's16le', '-acodec', 'pcm_s16le', '-']
    r = subprocess.run(cmd, capture_output=True)
    ff = list(array.array('h', r.stdout))
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_name', '-of', 'csv=p=0', wp],
                           capture_output=True, text=True).stdout.strip()
    res = []
    for m in 'ABC':
        x = xbox_mono(data, m)
        n = min(len(x), len(ff))
        eq = sum(1 for a, b in zip(x[:n], ff[:n]) if a == b)
        res.append('%s: len %d, exact %d/%d' % (m, len(x), eq, n))
    print(nm, 'probe=%s forced=%s ffmpeg_len=%d err=%r' % (probe, forced, len(ff), r.stderr[:80]), ' | '.join(res))
