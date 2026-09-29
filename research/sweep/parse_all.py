"""Step 2: try to parse EVERY XML1 text-XML file with convert_zone.parse_text_xml and classify failures.

Scans xml1_loose/ and the loose (non-.fb) files in xml1_assets/.
Writes parse_results.json: {path: {"ok": bool, "err": str, "diag": {...}}}
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json, os, re, sys, collections
import xml.etree.ElementTree as ET

sys.path.insert(0, _REPO + r'/tools')
import convert_zone, xmlb

ROOTS = {'loose': _REPO + r'/xml1_loose', 'assets': _REPO + r'/xml1_assets'}
EXTS = {'.xml', '.eng', '.fre', '.ger', '.chr', '.nav', '.ita', '.spa'}
OUT = _REPO + r'/research/sweep/parse_results.json'


def diag(raw):
    d = {}
    d['has_bom'] = raw.startswith(b'\xef\xbb\xbf')
    d['utf16'] = raw[:2] in (b'\xff\xfe', b'\xfe\xff')
    d['high_bytes'] = sum(1 for b in raw if b > 0x7f)
    d['nul_bytes'] = raw.count(b'\0')
    d['ctrl_bytes'] = sum(1 for b in raw if b < 0x20 and b not in (9, 10, 13))
    d['xml_decl'] = bool(re.search(rb'<\?xml', raw))
    d['comments'] = raw.count(b'<!--')
    d['cdata'] = raw.count(b'<![CDATA[')
    d['doctype'] = raw.count(b'<!DOCTYPE')
    d['named_entities'] = sorted(set(m.decode('latin-1') for m in re.findall(rb'&([A-Za-z][A-Za-z0-9]*);', raw)
                                     if m not in (b'amp', b'lt', b'gt', b'quot', b'apos')))
    d['double_dash_in_comment'] = len(re.findall(rb'<!--(?:(?!-->).)*?--(?!>)', raw, re.S))
    # bare '<' inside attribute values
    d['lt_in_attr'] = len(re.findall(rb'="[^"]*<[^"]*"', raw))
    return d


def strict_error(raw):
    """What would a strict parser say (after only stripping the xml decl and wrapping)?"""
    r = re.sub(rb'<\?xml[^>]*\?>', b'', raw)
    try:
        ET.fromstring(b'<?xml version="1.0" encoding="latin-1"?><w>' + r + b'</w>')
        return None
    except ET.ParseError as e:
        return str(e)


def context(raw, err):
    m = re.search(r'line (\d+), column (\d+)', err)
    if not m:
        return None
    ln, col = int(m.group(1)), int(m.group(2))
    lines = raw.split(b'\n')
    # parse_text_xml wraps with '<?xml ...?><xmlb_multiple_roots>' on line 1: column offsets shift on line 1 only
    if 1 <= ln <= len(lines):
        return lines[ln - 1][max(0, col - 80):col + 80].decode('latin-1')
    return None


def main():
    results = {}
    for tag, root in ROOTS.items():
        for d, _, files in os.walk(root):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext not in EXTS:
                    continue
                p = os.path.join(d, f)
                rel = tag + ':' + os.path.relpath(p, root).replace(os.sep, '/')
                raw = open(p, 'rb').read()
                rec = {'size': len(raw)}
                try:
                    el = convert_zone.parse_text_xml(p)
                    rec['ok'] = True
                    rec['root'] = el.tag
                    # also check it survives XMLB encoding (latin-1 only strings)
                    try:
                        xmlb.encode(el)
                    except Exception as e:
                        rec['ok'] = False
                        rec['err'] = 'xmlb.encode: %r' % e
                except ET.ParseError as e:
                    rec['ok'] = False
                    rec['err'] = str(e)
                    rec['context'] = context(raw, str(e))
                except Exception as e:
                    rec['ok'] = False
                    rec['err'] = '%s: %s' % (type(e).__name__, e)
                rec['strict_err'] = strict_error(raw)
                rec['diag'] = diag(raw)
                results[rel] = rec
    json.dump(results, open(OUT, 'w'), indent=1)
    bad = {k: v for k, v in results.items() if not v['ok']}
    print('parsed', len(results), 'failed', len(bad))
    for k, v in sorted(bad.items()):
        print(k, '|', v['err'], '|', (v.get('context') or '')[:160])
    c = collections.Counter()
    for k, v in results.items():
        for e in v['diag']['named_entities']:
            c[e] += 1
    print('named entities:', c.most_common())
    print('files with high bytes:', sum(1 for v in results.values() if v['diag']['high_bytes']))
    print('files with BOM:', sum(1 for v in results.values() if v['diag']['has_bom']))
    print('files utf16:', sum(1 for v in results.values() if v['diag']['utf16']))
    print('files with ctrl bytes:', sum(1 for v in results.values() if v['diag']['ctrl_bytes']))
    print('files with nul bytes:', sum(1 for v in results.values() if v['diag']['nul_bytes']))
    print('strict failures (only & fix skipped):', sum(1 for v in results.values() if v['strict_err']))


if __name__ == '__main__':
    main()
