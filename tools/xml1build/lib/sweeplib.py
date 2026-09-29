"""Shared helpers for the whole-game sweep: the robust XML1 text-XML parser the build uses (xml1build.common).

Was research/sweep/sweeplib.py (BUILDER_DESIGN.md 1.5; SPEC.md 27.13); that file is now a shim that also keeps the
sweep scripts' developer folders X1 / X1A / X2. No paths here: callers pass them."""
import os, re
import xml.etree.ElementTree as ET

import xmlb     # tools/xmlb.py (tools/ is on sys.path wherever the xml1build package is importable)

_ATTR_VAL = re.compile(rb'(=\s*")([^"]*)(")')


def normalise_text_xml(raw):
    """XML1 text XML -> bytes a strict parser accepts, preserving what XML1's lenient parser saw.

    1. drop <?xml ...?> declarations
    2. escape bare '&' that is not already an entity (credits.*, personal/magma04.*)
    3. escape '<' / '>' inside double-quoted attribute values (ui/menus/characters.*: "At < 20% Health",
       dialogs/mansion1a_2_hint.fre/.ger: "<arrow>"/"<Pfeile>")
    4. drop stray '/>' text after a closing tag (data/shared_combat_events.xml line 40 '</event>/>',
       data/fightstyles/fightstyle_gun_rifle.* line 7 '.../>/>')
    """
    raw = re.sub(rb'<\?xml[^>]*\?>', b'', raw)
    raw = re.sub(rb'&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', b'&amp;', raw)
    raw = _ATTR_VAL.sub(lambda m: m.group(1) + m.group(2).replace(b'<', b'&lt;').replace(b'>', b'&gt;')
                        + m.group(3), raw)
    raw = re.sub(rb'>\s*/>', b'>', raw)
    return raw


def parse_text_xml_robust(path_or_bytes):
    raw = open(path_or_bytes, 'rb').read() if isinstance(path_or_bytes, str) else path_or_bytes
    raw = normalise_text_xml(raw)
    wrapper = ET.fromstring(b'<?xml version="1.0" encoding="latin-1"?><%s>%s</%s>'
                            % (xmlb.MULTI_ROOT.encode(), raw, xmlb.MULTI_ROOT.encode()))
    for el in wrapper.iter():
        # XML2 attribute lookup is a binary search: lowercase + sorted. On a case-collision
        # (ps_sentinel_spider: PowerAttack/powerattack) keep the lowercase original's value.
        items = {}
        for k, v in el.attrib.items():
            lk = k.lower()
            if lk in items and k != lk:
                continue
            items[lk] = v
        el.attrib = dict(sorted(items.items()))
    return wrapper[0] if len(wrapper) == 1 else wrapper


def load_xmlb(path):
    return xmlb.decode(open(path, 'rb').read())


def walk_files(root):
    """{lower relpath with forward slashes: absolute path}"""
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root).replace(os.sep, '/').lower()] = p
    return out
