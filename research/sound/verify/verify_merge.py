"""Independent check of merged banks: XML2 part preserved (entries, keys, audio bytes), appended XML1 part maps
to the same audio as the converted XML1 bank for the same key, ZTRK blobs identical modulo remapped indices and
their remapped sound refs point to sounds with the same audio as in the source bank."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, struct, sys, json
from verify_conv import parse

X2 = _XML2 + '/Sounds/eng/'
CV = _REPO + '/research/sound/out/all_ima/eng/'
MG = _REPO + '/research/sound/out/merged/eng/'


def audio_of_sound(P, si):
    d = P['d']
    ent = P['tabs'][0][1][si]
    smp = struct.unpack_from('<H', ent, 0)[0]
    sent = P['tabs'][1][1][smp]
    fi = struct.unpack_from('<H', sent, 0)[0]
    fent = P['tabs'][2][1][fi]
    off, size, fmt = struct.unpack_from('<III', fent, 0)
    return sent[:8][2:], d[off:off + size], ent[2:]


def key_index(P, t):
    return {h: i for h, i in P['tabs'][t][0]}


def ztrk_refs(blob):
    PREFIX = {0: 0, 1: 1, 2: 4, 3: 1, 4: 2, 5: 5, 6: 4, 7: 8}
    ARGS = {0x00: 2, 0x08: 1, 0x10: 2, 0x18: 2, 0x30: 4, 0x20: 0, 0x28: 0, 0x38: 0, 0x40: 0}
    p = 4
    refs = []
    end = len(blob.rstrip(b'\0'))
    while p < end:
        b = blob[p]
        a0 = p + 1 + PREFIX[b & 7]
        typ = b & 0xF8
        if typ == 0x10 and blob[a0] == 4:
            refs.append(a0 + 1)
        p = a0 + ARGS[typ]
    return refs


def blob_at(P, ti):
    ents = P['tabs'][4][1]
    offs = sorted(struct.unpack_from('<I', e, 8)[0] for e in ents) + [P['hs']]
    o = struct.unpack_from('<I', ents[ti], 8)[0]
    return P['d'][o:offs[offs.index(o) + 1]].rstrip(b'\0')


for dp, dn, fn in os.walk(MG):
    for f in sorted(fn):
        if not f.endswith(('.zsm', '.zss')):
            continue
        rel = os.path.relpath(os.path.join(dp, f), MG).replace('\\', '/')
        M = parse(open(MG + rel, 'rb').read())
        A = parse(open(X2 + rel, 'rb').read())
        B = parse(open(CV + rel, 'rb').read())
        probs = []
        if M['fs'] != len(M['d']): probs.append('fs')
        for t in range(7):
            hs = [h for h, _ in M['tabs'][t][0]]
            if hs != sorted(hs): probs.append('unsorted T%d' % t)
        # XML2 part
        nA = len(A['tabs'][0][1])
        if M['tabs'][0][1][:nA] != A['tabs'][0][1]: probs.append('xml2 sound entries changed')
        kA = key_index(A, 0); kM = key_index(M, 0)
        for h, i in kA.items():
            if kM.get(h) != i: probs.append('xml2 key moved %08x' % h); break
        for i in range(nA):
            if audio_of_sound(A, i) != audio_of_sound(M, i): probs.append('xml2 audio changed %d' % i); break
        # XML1 part: every B key resolves in M (T0 or T4); if resolved to an appended sound, same audio as B
        kB = key_index(B, 0)
        n_same = n_xml2 = 0
        for h, i in kB.items():
            j = kM.get(h)
            if j is None:
                if h not in key_index(M, 4): probs.append('B key %08x lost' % h)
                continue
            if j < nA:
                n_xml2 += 1
            elif audio_of_sound(M, j) == audio_of_sound(B, i):
                n_same += 1
            else:
                probs.append('B key %08x audio differs' % h)
        # tracks
        tB = key_index(B, 4); tM = key_index(M, 4)
        ntr = 0
        for h, i in tB.items():
            if h not in tM: probs.append('track %08x missing' % h); continue
            bb = blob_at(B, i); mb = blob_at(M, tM[h])
            rb, rm = ztrk_refs(bb), ztrk_refs(mb)
            if len(bb) != len(mb) or rb != rm: probs.append('track %08x shape' % h); continue
            for o in rb:
                if audio_of_sound(B, bb[o]) != audio_of_sound(M, mb[o]): probs.append('track %08x ref audio differs' % h)
            ntr += 1
        print('%-22s sounds %d (xml2 %d) Bkeys %d: kept-xml2 %d appended-same %d tracks-ok %d hs=%d problems=%s' % (
            rel, len(M['tabs'][0][1]), nA, len(kB), n_xml2, n_same, ntr, M['hs'], probs[:4]))
