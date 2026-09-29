"""Table of tools/fix_music.py batch results (reads <banks>/_fix_music_report.json).

python summarize_batch.py [banks_dir]
"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'banks', 'eng')
reps = json.load(open(os.path.join(d, '_fix_music_report.json')))
bad = [r for r in reps if 'error' in r or 'skipped' in r]
ok = [r for r in reps if 'samples' in r]
a_frames = {}
for r in ok:
    b = os.path.basename(r['out'])
    if b.endswith('_a.zss'):
        a_frames[b[:-6]] = r['samples'][0]['layer_frames']
rows = []
agg = {'v0_near_minus_else_db': [], 'v0_click': [], 'mix_click': [], 'v0_snr': [], 'v1_snr': [], 'mix_snr': [],
       'plain_snr': []}
print(f'{len(ok)} banks ok, {len(bad)} failed/skipped')
print('bank          flags rate  sec   layer==_a pad0 joins      v0 SNR  v0 err near/else dBFS  v0clk  v1 SNR  mix SNR mixclk hold(min/med/max)')
for r in sorted(ok, key=lambda r: os.path.basename(r['out'])):
    b = os.path.basename(r['out'])
    for s in r['samples']:
        v = s['voices']
        if s['flags_out'] == '0x22':
            z = b[:-6]
            sp = s['split']
            v0 = v[0]
            near, els = v0['seams']['near_seams'], v0['seams']['elsewhere']
            agg['v0_near_minus_else_db'].append(near['err_rms_dbfs'] - els['err_rms_dbfs'])
            agg['v0_click'].append(v0['click_ratio'])
            agg['mix_click'].append(s['combat_mix']['click_ratio'])
            agg['v0_snr'].append(v0['snr_db'])
            agg['v1_snr'].append(v[1]['snr_db'])
            agg['mix_snr'].append(s['combat_mix']['snr_db'])
            h = s.get('hold_frames', {})
            print(f"{b:13s} {s['flags_out']:5s} {s['rate_out']:5d} {s['seconds']:6.1f} "
                  f"{str(a_frames.get(z) == s['layer_frames']):9s} {sp.get('layer0_unplayed_pad_peak', '-')!s:4s} "
                  f"{str(s['layer_join_jump']):10s} {v0['snr_db']:6.2f}  {near['err_rms_dbfs']:6.1f}/{els['err_rms_dbfs']:6.1f}"
                  f"          {v0['click_ratio']:5.2f}  {v[1]['snr_db']:6.2f}  {s['combat_mix']['snr_db']:6.2f} "
                  f"{s['combat_mix']['click_ratio']:5.2f}  {h.get('min')}/{h.get('median')}/{h.get('max')}")
        else:
            agg['plain_snr'].append(v[0]['snr_db'])
            print(f"{b:13s} {s['flags_out']:5s} {s['rate_out']:5d} {s['seconds']:6.1f}  plain stereo      "
                  f"                {v[0]['snr_db']:6.2f}")
for k, x in agg.items():
    if x:
        print(f'{k:24s} min {min(x):7.2f}  median {float(np.median(x)):7.2f}  max {max(x):7.2f}  (n={len(x)})')
for r in bad:
    print('BAD', r)
