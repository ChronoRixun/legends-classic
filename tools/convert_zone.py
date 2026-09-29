"""Convert one XML1 zone (and everything its .fb bundle lists) into an XML2 install.

usage: convert_zone.py <xml1_loose> <xml2_install> <zone> [<zone> ...]
       zone = map path under maps/, e.g. nyc/alison/nyc1_1_1

Files XML2 already has are left alone (XML2's version wins) and listed at the end, so the
first tests run XML1 levels with XML2's shared assets and heroes.
"""
import json, os, re, sys
import xml.etree.ElementTree as ET
import xmlb

TEXT_EXTS = {'.xml': ['.XMLB'], '.eng': ['.XMLB', '.engb'], '.chr': ['.CHRB'], '.nav': ['.NAVB']}


def parse_text_xml(path):
    raw = open(path, 'rb').read()
    raw = re.sub(rb'<\?xml[^>]*\?>', b'', raw)
    # XML1 text files contain stray '&' and bytes > 0x7f; treat them as latin-1 literals
    raw = re.sub(rb'&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', b'&amp;', raw)
    wrapper = ET.fromstring(b'<?xml version="1.0" encoding="latin-1"?><%s>%s</%s>'
                            % (xmlb.MULTI_ROOT.encode(), raw, xmlb.MULTI_ROOT.encode()))
    # XML2's attribute lookup is a binary search: names must be lowercase and sorted
    for el in wrapper.iter():
        el.attrib = dict(sorted((k.lower(), v) for k, v in el.attrib.items()))
    return wrapper[0] if len(wrapper) == 1 else wrapper


class Converter:
    def __init__(self, x1, x2):
        self.x1, self.x2 = x1, x2
        self.manifest = json.load(open(os.path.join(x1, '_fb_manifest.json')))
        self.existing = {}
        for d, _, files in os.walk(x2):
            for f in files:
                p = os.path.relpath(os.path.join(d, f), x2).replace(os.sep, '/').lower()
                self.existing[p] = os.path.join(d, f)
        self.original = set(self.existing)
        self.written, self.kept_xml2, self.missing = [], [], []

    def exists_in_xml2(self, rel_noext, exts):
        return any((rel_noext + e).lower() in self.existing for e in exts)

    def is_original(self, rel_noext, exts):
        return any((rel_noext + e).lower() in self.original for e in exts)

    def emit(self, rel_noext, ext, data):
        dst = os.path.join(self.x2, rel_noext + ext)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(data)
        self.existing[(rel_noext + ext).lower()] = dst
        self.written.append(rel_noext + ext)

    def convert_file(self, name, force=False, patch=None):
        """Convert one XML1 loose file into XML2 form. Returns the extensionless path."""
        rel_noext, ext = os.path.splitext(name)
        src = os.path.join(self.x1, name)
        if not os.path.exists(src):
            self.missing.append(name)
            return rel_noext
        if ext in TEXT_EXTS:
            outs = TEXT_EXTS[ext]
            if not force and self.exists_in_xml2(rel_noext, outs):
                if self.is_original(rel_noext, outs):
                    self.kept_xml2.append(name)
                return rel_noext
            root = parse_text_xml(src)
            if patch:
                patch(root)
            data = xmlb.encode(root)
            for out in outs:
                self.emit(rel_noext, out, data)
        else:
            if not force and self.exists_in_xml2(rel_noext, [ext, ext.upper()]):
                if self.is_original(rel_noext, [ext, ext.upper()]):
                    self.kept_xml2.append(name)
                return rel_noext
            self.emit(rel_noext, ext, open(src, 'rb').read())
        return rel_noext

    def zone(self, zone):
        bundle = f'packages/generated/maps/{zone}.fb'
        entries = self.manifest[bundle]
        script = f'scripts/{zone}.py'

        def patch_world(root):
            for el in root.iter('entity'):
                if el.get('name') == 'world' and 'zonescript' not in el.attrib \
                        and os.path.exists(os.path.join(self.x1, script)):
                    el.set('zonescript', zone)
                    break

        pkg = ET.Element('packagedef')
        seen = set()
        for name, kind in entries:
            if name in ('on', 'off'):
                ET.SubElement(pkg, kind, filename=name)
                continue
            if name.endswith(('.fre', '.ger')):
                continue
            is_zone_file = name.startswith(f'maps/{zone}.')
            rel = self.convert_file(name, force=is_zone_file,
                                    patch=patch_world if kind == 'zonexml' else None)
            if (kind, rel) not in seen:
                seen.add((kind, rel))
                ET.SubElement(pkg, kind, filename=rel)
        if os.path.exists(os.path.join(self.x1, script)):
            self.convert_file(script, force=True)
            ET.SubElement(pkg, 'script', filename=f'scripts/{zone}')
        # XML2 zones carry an AI buoy network; XML1 has none, so give the loader an empty one
        self.emit(f'maps/{zone}', '.BOYB', xmlb.encode(ET.Element('buoy')))
        ET.SubElement(pkg, 'boy', filename=f'maps/{zone}')
        self.emit(f'packages/generated/maps/{zone}', '.PKGB', xmlb.encode(pkg))
        self.add_zoneinfo(zone)

    def add_zoneinfo(self, zone):
        path = self.existing['data/zoneinfo.xmlb']
        root = xmlb.decode(open(path, 'rb').read())
        if not any(z.get('name') == zone for z in root):
            ET.SubElement(root, 'zone', act='1', build='normal', name=zone, state='1')
            open(path, 'wb').write(xmlb.encode(root))


if __name__ == '__main__':
    x1, x2, *zones = sys.argv[1:]
    c = Converter(x1, x2)
    for z in zones:
        c.zone(z)
    print(f'wrote {len(c.written)} files; kept XML2 version of {len(c.kept_xml2)}; missing {len(c.missing)}')
    for m in c.missing:
        print('  missing', m)
    print('kept XML2:', ', '.join(sorted(set(c.kept_xml2))[:40]))
