import collections, glob, sys
import xmlb
root = sys.argv[1]
exts = ('.xmlb', '.engb', '.chrb', '.navb', '.boyb', '.pkgb')
ok, bad = 0, collections.Counter()
examples = {}
for f in glob.glob(root + '/**/*', recursive=True):
    if not f.lower().endswith(exts):
        continue
    data = open(f, 'rb').read()
    try:
        if xmlb.encode(xmlb.decode(data)) == data:
            ok += 1
            continue
        reason = 'mismatch'
    except Exception as e:
        reason = type(e).__name__ + ': ' + str(e)[:60]
    bad[reason] += 1
    examples.setdefault(reason, f)
print('roundtrip ok', ok, 'failed', sum(bad.values()))
for r, n in bad.most_common(10):
    print(n, r, examples[r])
