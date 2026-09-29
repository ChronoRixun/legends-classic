"""Verify the robust normaliser (sweeplib.parse_text_xml_robust) on EVERY XML1 text-XML file:
parse -> xmlb.encode -> xmlb.decode round trip must be canonically identical; report files where the
normaliser changed anything relative to the stock convert_zone.parse_text_xml."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, json
sys.path.insert(0, _REPO + r'/research/sweep')
sys.path.insert(0, _REPO + r'/tools')
from sweeplib import parse_text_xml_robust, X1, X1A
import convert_zone, xmlb


def canon(el):
    return (el.tag, tuple(el.attrib.items()), tuple(canon(c) for c in el))


ok = fail = changed = 0
fails, diffs = {}, []
for root in (X1, X1A):
    for d, _, fs in os.walk(root):
        for f in fs:
            if os.path.splitext(f)[1].lower() not in ('.xml', '.eng', '.fre', '.ger', '.chr', '.nav'):
                continue
            p = os.path.join(d, f)
            rel = os.path.relpath(p, root).replace(os.sep, '/')
            try:
                el = parse_text_xml_robust(p)
                data = xmlb.encode(el)
                back = xmlb.decode(data)
                if canon(back) != canon(el):
                    raise ValueError('round trip mismatch')
                ok += 1
            except Exception as e:
                fail += 1
                fails[rel] = str(e)
                continue
            try:
                stock = convert_zone.parse_text_xml(p)
                if canon(stock) != canon(el):
                    changed += 1
                    diffs.append(rel)
            except Exception as e:
                changed += 1
                diffs.append(rel + ' (stock parser fails: %s)' % e)
print('robust parse+encode+decode ok', ok, 'fail', fail, fails)
print('files where robust result differs from stock parser:', changed)
for x in diffs:
    print('  ', x)
el = parse_text_xml_robust(os.path.join(X1, 'ui/menus/characters.eng'))
print('characters.eng sample:', [i.get('value') for i in el.iter('listitem') if '<' in (i.get('value') or '')])
el = parse_text_xml_robust(os.path.join(X1, 'dialogs/mansion1a_2_hint.fre'))
print('mansion1a_2_hint.fre sample:', [e.get('text')[:90] for e in el.iter('dialog') if '<' in (e.get('text') or '')][:1])
