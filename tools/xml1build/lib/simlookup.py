"""Offline simulation of XMen2.exe's sound-name resolution (0x590bd0 -> 0x590e50 -> 0x595780/0x595720):
  1. '\\' -> '/' (0x5924e0)
  2. if a zone soundfile is loaded and name starts with 'death_style' (11 chars, _strnicmp) or 'zone_sh' (7 chars):
     name = '<soundfile>/' + name   (0x590c2c..0x590c60)
  3. h = ELF-hash(upper(name)); for each loaded bank: track table, then sound table, then
     hash('/***RANDOM***/0', seed=h) in the sound table (0x590e50)
Usage: simlookup.py --zone nyc1 --banks b1 b2 ... --names n1 n2 ... | --names-from file.xml ..."""
import sys, re
from . import zsnd
from .zhash import elf_hash

def load_banks(paths):
    out = []
    for p in paths:
        b = zsnd.load(p, strict=False)
        out.append((p, {h for s in b.sounds for h in s.hashes}, {h for t in b.tracks for h in t.hashes}))
    return out

def resolve(name, zone, banks):
    n = name.replace('\\', '/')
    if zone and (n[:11].lower() == 'death_style' or n[:7].lower() == 'zone_sh'):
        n = zone + '/' + n
    h = elf_hash(n)
    h0 = elf_hash('/***RANDOM***/0', h)
    for p, snd, trk in banks:
        if h in trk:
            return n, p, 'track'
        if h in snd:
            return n, p, 'sound'
        if h0 in snd:
            k = 0
            while elf_hash('/***RANDOM***/%d' % k, h) in snd:
                k += 1
            return n, p, 'random x%d' % k
    return n, None, None

def names_from(files):
    rx = re.compile(r'\b([a-z_0-9]*sound[a-z_0-9]*|soundtoplay[b]?)\s*=\s*"([^"]+)"', re.I)
    out = []
    for f in files:
        t = open(f, 'rb').read().decode('latin-1')
        for m in rx.finditer(t):
            k, v = m.group(1).lower(), m.group(2)
            if k in ('soundfile', 'sounddir') or re.fullmatch(r'[-0-9. ]+', v) or 'radius' in k or 'volume' in k:
                continue
            out.append(v)
        for m in re.finditer(r'play\w*sound\w*\s*\(\s*"([^"]+)"', t, re.I):
            out.append(m.group(1))
    return out

if __name__ == '__main__':
    args = sys.argv[1:]
    zone = None; banks = []; names = []; mode = None
    for a in args:
        if a in ('--zone', '--banks', '--names', '--names-from'):
            mode = a; continue
        if mode == '--zone': zone = a
        elif mode == '--banks': banks.append(a)
        elif mode == '--names': names.append(a)
        elif mode == '--names-from': names += names_from([a])
    B = load_banks(banks)
    ok = 0
    seen = set()
    for n in names:
        if n.lower() in seen:
            continue
        seen.add(n.lower())
        full, bank, kind = resolve(n, zone, B)
        ok += bank is not None
        print('%-5s %-45s -> %-50s %s %s' % ('OK' if bank else 'MISS', n, full, (bank or '').split('/eng/')[-1], kind or ''))
    print('resolved %d / %d distinct names' % (ok, len(seen)))
