"""Step 2b: second-order text-XML hazards that parse "fine" but would lose/alter data in XMLB.

- element text/tail content (XMLB has no text nodes -> silently dropped)
- attribute names that collide after lowercasing (dict() keeps only the last)
- '<' inside attribute values (fails to parse) and high-byte histogram
- entity usage (&amp; etc.) whose meaning depends on whether XML1's parser decoded entities
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json, os, re, sys, collections
import xml.etree.ElementTree as ET

sys.path.insert(0, _REPO + r'/tools')
import convert_zone

ROOTS = {'loose': _REPO + r'/xml1_loose', 'assets': _REPO + r'/xml1_assets'}
EXTS = {'.xml', '.eng', '.fre', '.ger', '.chr', '.nav'}


def lenient_parse(raw):
    raw = re.sub(rb'<\?xml[^>]*\?>', b'', raw)
    raw = re.sub(rb'&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', b'&amp;', raw)
    # escape '<' and '>' inside double-quoted attribute values of start tags
    raw = re.sub(rb'(=\s*")([^"]*)(")', lambda m: m.group(1) + m.group(2).replace(b'<', b'&lt;').replace(b'>', b'&gt;') + m.group(3), raw)
    return ET.fromstring(b'<?xml version="1.0" encoding="latin-1"?><w>' + raw + b'</w>')


def main():
    text_nodes = collections.defaultdict(list)
    case_collide = collections.defaultdict(list)
    upper_attr = collections.Counter()
    hb = collections.defaultdict(collections.Counter)
    entity_files = collections.defaultdict(list)
    fails = {}
    multi_root = []
    for tag, root in ROOTS.items():
        for d, _, files in os.walk(root):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext not in EXTS:
                    continue
                p = os.path.join(d, f)
                rel = tag + ':' + os.path.relpath(p, root).replace(os.sep, '/')
                raw = open(p, 'rb').read()
                for b in raw:
                    if b > 0x7f:
                        hb[ext][b] += 1
                for ent in set(re.findall(rb'&(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);', raw)):
                    entity_files[ent.decode()].append(rel)
                # attribute case collisions need the raw attribute lists
                for m in re.finditer(rb'<([A-Za-z_][\w.\-]*)((?:\s+[\w.\-:]+\s*=\s*"[^"]*")*)\s*/?>', raw):
                    names = re.findall(rb'([\w.\-:]+)\s*=\s*"', m.group(2))
                    low = [n.lower() for n in names]
                    if len(set(low)) != len(low):
                        case_collide[rel].append(m.group(0)[:200].decode('latin-1'))
                    for n in names:
                        if n != n.lower():
                            upper_attr[n.decode()] += 1
                try:
                    w = lenient_parse(raw)
                except ET.ParseError as e:
                    fails[rel] = str(e)
                    continue
                if len(w) > 1:
                    multi_root.append((rel, [c.tag for c in w][:5], len(w)))
                for el in w.iter():
                    if el is w:
                        continue
                    if el.text and el.text.strip():
                        text_nodes[rel].append((el.tag, el.text.strip()[:80]))
                    if el.tail and el.tail.strip():
                        text_nodes[rel].append(('tail-of-' + el.tag, el.tail.strip()[:80]))
    out = {
        'lenient_fail': fails,
        'text_nodes': {k: v[:10] + [('...total', str(len(v)))] for k, v in text_nodes.items()},
        'attr_case_collisions': dict(case_collide),
        'uppercase_attr_names': upper_attr.most_common(),
        'high_bytes_by_ext': {e: {hex(b): n for b, n in c.most_common()} for e, c in hb.items()},
        'entity_usage': {k: (len(v), v[:15]) for k, v in entity_files.items()},
        'multi_root_files': multi_root,
    }
    json.dump(out, open(_REPO + r'/research/sweep/parse_extra.json', 'w'), indent=1)
    print('lenient fails:', fails)
    print('files with text nodes:', len(text_nodes))
    for k, v in list(text_nodes.items())[:30]:
        print('  ', k, len(v), v[:3])
    print('attr case collisions:', len(case_collide))
    for k, v in list(case_collide.items())[:20]:
        print('  ', k, v[:2])
    print('uppercase attr names:', upper_attr.most_common(40))
    for e, c in hb.items():
        print('high bytes', e, [(hex(b), n) for b, n in c.most_common(25)])
    print('entities:', {k: len(v) for k, v in entity_files.items()})
    print('multi-root files:', len(multi_root), multi_root[:20])


if __name__ == '__main__':
    main()
