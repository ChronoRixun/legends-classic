"""Shared helpers for the characters workstream (read-only access to both games)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import hashlib, json, os, re, sys
import xml.etree.ElementTree as ET

sys.path.insert(0, _REPO + '/tools')
import xmlb  # noqa: E402

X2 = _XML2
X1L = _REPO + '/xml1_loose'
X1A = _REPO + '/xml1_assets'
HERE = _REPO + '/research/characters'


def parse_x1_text(path, lower=False):
    """Parse an XML1 text XML file (possibly several roots). Keeps attribute case unless lower=True.
    Mirrors tools/convert_zone.parse_text_xml (stray '&' -> &amp;, latin-1)."""
    raw = open(path, 'rb').read()
    raw = re.sub(rb'<\?xml[^>]*\?>', b'', raw)
    raw = re.sub(rb'&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', b'&amp;', raw)
    w = ET.fromstring(b'<?xml version="1.0" encoding="latin-1"?><%s>%s</%s>'
                      % (xmlb.MULTI_ROOT.encode(), raw, xmlb.MULTI_ROOT.encode()))
    if lower:
        for el in w.iter():
            el.attrib = dict(sorted((k.lower(), v) for k, v in el.attrib.items()))
    return w[0] if len(w) == 1 else w


def load_xmlb(path):
    return xmlb.decode(open(path, 'rb').read())


_x2_index = None


def x2_index():
    """lowercase relpath -> real path for every file in the XML2 install."""
    global _x2_index
    if _x2_index is None:
        _x2_index = {}
        for d, _, files in os.walk(X2):
            for f in files:
                p = os.path.join(d, f)
                _x2_index[os.path.relpath(p, X2).replace(os.sep, '/').lower()] = p
    return _x2_index


def x1_files(root=X1L):
    out = {}
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, root).replace(os.sep, '/')
            if rel == '_fb_manifest.json':
                continue
            out[rel.lower()] = p
    return out


def sha1(path):
    return hashlib.sha1(open(path, 'rb').read()).hexdigest()


def canon(el):
    """Canonical, order-preserving representation of an element tree with attribute names
    lowercased+sorted and tag case folded (XMLB lookup of tags is case-insensitive for our
    comparison purposes)."""
    return (el.tag.lower(), tuple(sorted((k.lower(), v) for k, v in el.attrib.items())),
            tuple(canon(c) for c in el))


def manifest():
    return json.load(open(os.path.join(X1L, '_fb_manifest.json')))
