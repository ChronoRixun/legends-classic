"""List every XML1 bank and which XML1 zones / characters use it (soundfile= on zone world entities,
sounddir= in npcstat/herostat), and flag name collisions with XML2's bank set."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, collections
import xml.etree.ElementTree as ET
import zsnd

XML1_BANKS = _REPO + '/xml1_xbox/sounds/zsds'
XML2_BANKS = _XML2 + '/Sounds/eng'
ROOTS = [_REPO + '/xml1_loose', _REPO + '/xml1_assets']
OUT = _REPO + '/research/sound'

def banks(root):
    d = {}
    for p in zsnd.iter_banks(root):
        rel = os.path.relpath(p, root).replace('\\', '/')
        d[os.path.basename(rel)] = rel
    return d

def main():
    x1 = banks(XML1_BANKS)
    x2 = banks(XML2_BANKS)
    sf = collections.defaultdict(set)   # soundfile value -> zone files
    sd = collections.defaultdict(set)   # sounddir -> characters
    seen = set()
    rx_sf = re.compile(r'\bsoundfile\s*=\s*"([^"]*)"', re.I)
    rx_sd = re.compile(r'\bsounddir\s*=\s*"([^"]*)"', re.I)
    rx_name = re.compile(r'\bname\s*=\s*"([^"]*)"', re.I)
    for root in ROOTS:
        for dp, dn, fn in os.walk(root):
            for f in fn:
                if not f.lower().endswith(('.xml', '.eng', '.chr')):
                    continue
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, root).replace('\\', '/').lower()
                txt = open(p, 'rb').read().decode('latin-1')
                for m in rx_sf.finditer(txt):
                    zone = re.sub(r'\.(xml|eng|fre|ger|chr)$', '', rel)
                    sf[m.group(1).lower()].add(zone)
                if 'sounddir' in txt.lower():
                    # per stat block: find enclosing element's name
                    for m in re.finditer(r'<(\w+)\b([^>]*)>', txt):
                        attrs = m.group(2)
                        d = rx_sd.search(attrs)
                        if d:
                            n = rx_name.search(attrs)
                            sd[d.group(1).lower()].add('%s:%s' % (os.path.basename(rel).split('.')[0], n.group(1) if n else '?'))
    rows = []
    used = set()
    for bank, rel in sorted(x1.items()):
        base = bank.rsplit('.', 1)[0]
        zone = re.sub(r'_[acdmv]$', '', base)
        users = []
        if re.search(r'_[acdmv]$', base) and zone in sf:
            users += ['zone:' + z for z in sorted(sf[zone])]
        if base in sd:
            users += ['char:' + c for c in sorted(sd[base])]
        if base in ('x_common', 'x_voice'):
            users.append('GLOBAL (engine: x_common.zsd / x_voice.zsd)')
        if base in ('menu_a', 'menu_c'):
            users.append('menus (music/menu_a)')
        b = zsnd.load(os.path.join(XML1_BANKS, rel))
        rows.append({'bank': rel, 'sounds': len(b.sounds), 'tracks': len(b.tracks), 'bytes': len(b.data),
                     'collides_with_xml2': bank in x2, 'used_by': users})
        if users:
            used.add(bank)
    unknown_sf = {k: sorted(v) for k, v in sf.items() if not any(x.startswith(k + '_') for x in x1)}
    unknown_sd = {k: sorted(v) for k, v in sd.items() if (k + '.zsm') not in x1 and (k + '.zss') not in x1}
    json.dump({'banks': rows, 'soundfile_values': {k: sorted(v) for k, v in sf.items()},
               'sounddir_values': {k: sorted(v) for k, v in sd.items()},
               'soundfile_without_bank': unknown_sf, 'sounddir_without_bank': unknown_sd},
              open(os.path.join(OUT, 'xml1_bank_usage.json'), 'w'), indent=1)
    with open(os.path.join(OUT, 'xml1_bank_usage.txt'), 'w') as fh:
        for r in rows:
            fh.write('%-22s snd=%4d trk=%3d %9d B %s  %s\n' % (r['bank'], r['sounds'], r['tracks'], r['bytes'],
                     'COLLIDES' if r['collides_with_xml2'] else '        ', '; '.join(r['used_by']) or '(no reference found)'))
        fh.write('\nsoundfile values with no bank: %s\n' % json.dumps(unknown_sf))
        fh.write('sounddir values with no bank: %s\n' % json.dumps(unknown_sd))
    print(open(os.path.join(OUT, 'xml1_bank_usage.txt')).read())

if __name__ == '__main__':
    main()
