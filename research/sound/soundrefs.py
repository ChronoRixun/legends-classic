"""
Collect every sound reference from both games' data and resolve it against the sound banks by hash.

XML2: every XMLB-family file under the install (decoded with tools/xmlb.py) + Scripts/**/*.py
XML1: every text xml-ish file under xml1_loose + xml1_assets (+ scripts)

A "sound reference" = attribute whose name contains 'sound' (or known voice/music attrs), or any
attribute/script string value that resolves to a sound-bank key.
Outputs JSON + text summary into research/sound/.
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, sys, json, collections
import xml.etree.ElementTree as ET
sys.path.insert(0, _REPO + '/tools')
import xmlb
import zsnd
from zhash import elf_hash

OUT = _REPO + '/research/sound'
XML2 = _XML2
XML1_LOOSE = _REPO + '/xml1_loose'
XML1_ASSETS = _REPO + '/xml1_assets'
BANKS = {'xml2': XML2 + '/Sounds/eng', 'xml1': _REPO + '/xml1_xbox/sounds/zsds'}
XMLB_EXT = ('.xmlb', '.engb', '.chrb', '.navb', '.boyb', '.pkgb')
TXT_EXT = ('.xml', '.eng', '.chr', '.nav', '.boy', '.pkg')


def bank_index(root):
    """hash -> list of (bank_relpath, kind) ; kind in sound/track"""
    idx = collections.defaultdict(list)
    for p in zsnd.iter_banks(root):
        b = zsnd.load(p, strict=False)
        rel = os.path.relpath(p, root).replace('\\', '/')
        for s in b.sounds:
            for h in s.hashes:
                idx[h].append((rel, 'sound'))
        for t in b.tracks:
            for h in t.hashes:
                idx[h].append((rel, 'track'))
    return idx


def iter_attrs_xml(root_el, path):
    for el in root_el.iter():
        for k, v in el.attrib.items():
            yield el.tag, k, v


def load_tree(path):
    low = path.lower()
    data = open(path, 'rb').read()
    if low.endswith(XMLB_EXT):
        try:
            return xmlb.decode(data)
        except Exception:
            return None
    try:
        txt = data.decode('latin-1')
        txt = re.sub(r'<\?xml[^>]*\?>', '', txt)
        return ET.fromstring('<__r>' + txt + '</__r>')
    except Exception:
        return None


def walk(root, exts):
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.lower().endswith(exts):
                yield os.path.join(dp, f).replace('\\', '/')


STR_RX = re.compile(r'["\']([A-Za-z0-9_\-./\\ ]{3,80})["\']')

def collect(game):
    refs = []  # (file, tag, attr, value)
    if game == 'xml2':
        for p in walk(XML2, XMLB_EXT):
            t = load_tree(p)
            if t is None:
                continue
            for tag, k, v in iter_attrs_xml(t, p):
                refs.append((os.path.relpath(p, XML2).replace('\\', '/'), tag, k, v))
        script_root = XML2 + '/Scripts'
        base = XML2
    else:
        seen = set()
        for root in (XML1_LOOSE, XML1_ASSETS):
            for p in walk(root, TXT_EXT):
                rel = os.path.relpath(p, root).replace('\\', '/').lower()
                if rel in seen:
                    continue
                seen.add(rel)
                t = load_tree(p)
                if t is None:
                    continue
                for tag, k, v in iter_attrs_xml(t, p):
                    refs.append((rel, tag, k, v))
        script_root = None
        base = None
    scripts = []
    roots = [script_root] if script_root else [XML1_LOOSE, XML1_ASSETS]
    for r in roots:
        for p in walk(r, ('.py',)):
            txt = open(p, 'rb').read().decode('latin-1')
            for m in STR_RX.finditer(txt):
                scripts.append((os.path.relpath(p, r).replace('\\', '/'), 'script', 'str', m.group(1)))
    return refs, scripts


def norm(v):
    return v.replace('\\', '/').lower().strip()


def main():
    report = {}
    for game in ('xml2', 'xml1'):
        idx = bank_index(BANKS[game])
        refs, scripts = collect(game)
        attr_hits = collections.Counter()
        attr_total = collections.Counter()
        soundish_unresolved = collections.Counter()
        resolved = {}
        for f, tag, k, v in refs + scripts:
            if not v or len(v) > 120:
                continue
            h = elf_hash(norm(v))
            soundish = 'sound' in k.lower() or k.lower() in ('music', 'voice')
            if soundish:
                attr_total[k.lower()] += 1
            hit = idx.get(h)
            if not hit:
                h2 = elf_hash('/***RANDOM***/0', h)
                hit = idx.get(h2)
            if hit:
                attr_hits[(tag if tag != 'script' else 'script', k.lower())] += 1
                resolved.setdefault(norm(v), {'banks': sorted(set(b for b, _ in hit)), 'kinds': sorted(set(x for _, x in hit)), 'refs': []})
                if len(resolved[norm(v)]['refs']) < 5:
                    resolved[norm(v)]['refs'].append('%s <%s %s>' % (f, tag, k))
            elif soundish and not re.fullmatch(r'-?[0-9.]+|true|false', v.lower()):
                soundish_unresolved[(k.lower(), norm(v))] += 1
        report[game] = {
            'bank_keys': len(idx),
            'resolved_names': len(resolved),
            'resolved_keys_fraction': round(len(set(elf_hash(n) for n in resolved) & set(idx)) / max(1, len(idx)), 4),
            'attr_hits': {'%s/%s' % a: c for a, c in attr_hits.most_common()},
            'soundish_attr_totals': dict(attr_total.most_common()),
            'unresolved_soundish_sample': ['%s=%s (%d)' % (k, v, c) for (k, v), c in soundish_unresolved.most_common(80)],
            'unresolved_soundish_count': len(soundish_unresolved),
        }
        json.dump(resolved, open(os.path.join(OUT, 'soundrefs_%s.json' % game), 'w'), indent=1, sort_keys=True)
        print(game, json.dumps(report[game], indent=1)[:6000])
    json.dump(report, open(os.path.join(OUT, 'soundrefs_summary.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
