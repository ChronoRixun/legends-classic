"""XMen2.exe console queue (0x55c410) refuses a command when 2 are already pending ([+0x630]==2 -> return 0).
Find scripts (source XML1 vs rewritten) that issue >2 console-sending calls with no wait between them."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, sys
V = _REPO + '/research/scripts/verify'
senders = {s.lower() for s in json.load(open(V + '/console_senders.json'))}
WAIT = {'waittimed', 'waitsignal'}
CALL = re.compile(r'([A-Za-z_][A-Za-z0-9_.]*)\s*\(')


def runs(path):
    t = open(path, 'rb').read().decode('latin-1').replace('\r\n', '\n')
    best = cur = 0
    seq = []
    bestseq = []
    for line in t.split('\n'):
        s = line.split('#', 1)[0]
        for m in CALL.finditer(s):
            n = m.group(1).lower()
            if n.startswith('game.'):
                n = n[5:]
            if n in WAIT:
                cur = 0
                seq = []
            elif n in senders:
                cur += 1
                seq.append(n)
                if cur > best:
                    best, bestseq = cur, list(seq)
    return best, bestseq


for label, root in (('rewritten', _REPO + '/research/scripts/out/scripts'),):
    hits = []
    for dp, dn, fn in os.walk(root):
        for f in fn:
            p = os.path.join(dp, f)
            b, s = runs(p)
            if b > 2:
                hits.append((b, os.path.relpath(p, root), s))
    hits.sort(reverse=True)
    print(label, 'scripts with >2 console sends and no wait in between:', len(hits))
    for h in hits[:15]:
        print('   ', h)
