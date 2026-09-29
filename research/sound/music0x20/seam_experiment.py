"""Compare seam strategies for XML2's shared-state layered stream on a slice of an XML1 _c bank.

python seam_experiment.py [bank=nyc1_c] [chunks=60] [rate=44100|22050]
"""
import os, sys, json, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import fix_music as fm, zsnd  # noqa

name = sys.argv[1] if len(sys.argv) > 1 else 'nyc1_c'
nch = int(sys.argv[2]) if len(sys.argv) > 2 else 60
rate_out = int(sys.argv[3]) if len(sys.argv) > 3 else 44100
path = [p for p in zsnd.iter_banks(fm.XBOX_ROOT) if os.path.basename(p) == name + '.zss'][0]
b = zsnd.load(path)
s = b.samples[0]
pcm = fm.decode_file(b, b.files[0], 2)
layers, info = fm.split_layers(pcm, fm.xml1_chunk_frames(2))
rate = s.u32(4)
if rate_out != rate:
    layers, rate = fm.resample(layers, rate, rate_out)
C = fm.xml2_chunk_frames(2)
layers = [l[:, :nch * C + 3000] for l in layers]      # partial last chunk exercises the pad path too
print(name, 'rate', rate, 'frames/layer', layers[0].shape[1])

configs = [(c.split()[0], int(c.split()[1]), int(c.split()[2]), int(c.split()[3]), (c.split()[4:] or ['xfade'])[0]) for c in
           (os.environ.get('CFGS') or 'hard,0,0,0;f8h8,8,8,0;f4h4,4,4,0;f8h0,8,0,0;f16h16,16,16,0;f8h8H8,8,8,8;f8h8H16,8,8,16;f8h8H32,8,8,32').replace(',', ' ').split(';')]
for tag, fade, hold, head, mode in configs:
    t0 = time.time()
    target, w, wins, alt = fm.build_stream(layers, C, fade, None if hold < 0 else hold, head)
    data = fm.encode(target, w, wins, 'greedy')
    v, full, _ = fm.engine_voices(data, 2, 2)
    mix, ref = v[0] + v[1], layers[0] + layers[1]
    r0 = fm.seam_report(v[0], layers[0], C)
    r1 = fm.seam_report(v[1], layers[1], C)
    rm = fm.seam_report(mix, ref, C)
    print(json.dumps({'cfg': tag, 't': round(time.time() - t0, 1), 'st': alt,
                      'v0': [fm.snr_db(layers[0], v[0]), r0['near_seams']['snr_db'], r0['elsewhere']['snr_db'], r0['near_seams']['err_peak'],
                             fm.click_ratio(v[0], C)],
                      'v1': [fm.snr_db(layers[1], v[1]), r1['near_seams']['snr_db'], r1['elsewhere']['snr_db'], r1['near_seams']['err_peak'],
                             fm.click_ratio(v[1], C)],
                      'mix': [fm.snr_db(ref, mix), rm['near_seams']['snr_db'], rm['elsewhere']['snr_db'], rm['near_seams']['err_peak'],
                              fm.click_ratio(mix, C)],
                      'mix_err_near_dbfs': rm['near_seams']['err_rms_dbfs'], 'v1_err_near_dbfs': r1['near_seams']['err_rms_dbfs'], 'v0_err_near_dbfs': r0['near_seams']['err_rms_dbfs'], 'mix_err_else_dbfs': rm['elsewhere']['err_rms_dbfs'],
                      'src_click': [fm.click_ratio(layers[0], C), fm.click_ratio(layers[1], C), fm.click_ratio(ref, C)]}))
print('columns: [total SNR, near-seam SNR, elsewhere SNR, near-seam peak error, click ratio]')
