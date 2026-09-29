import sys, json
for l in sys.stdin:
    try: r=json.loads(l)
    except Exception: print(l.strip()); continue
    print(r['out'].replace(chr(92),'/').split('/eng/')[-1], 'enc',r['encoder'],'files',r['files'],'tracks',r['tracks'],'in',r['in_bytes'],'out',r['out_bytes'],'medianSNR',r['verify_snr_db_median'],'worst',r['verify_worst_file'][0],r['verify_worst_file'][1]['snr_db'],'%ss'%r['seconds'])
