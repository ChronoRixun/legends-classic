"""Audit the player's equipment without changing a build or shipping the source table.

Usage: python tools/equipment_report.py --items <items.eng> --values <values.xml> [--json]
Output goes only to stdout. Full means every bonus has a mapping, not that every
mapping is exact; approximate and unsupported reasons are reported independently.
Keep reports that identify your source items local.
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from xml1build.equipment import audit_equipment
from xml1build.heroes import Values
from xml1build.lib.sweeplib import parse_text_xml_robust


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--items', required=True, type=Path, help='your decoded XML1 equipment table')
    parser.add_argument('--values', required=True, type=Path, help='your XML1 values.xml')
    parser.add_argument('--json', action='store_true', help='machine-readable per-bonus report')
    args = parser.parse_args(argv)
    try:
        items = parse_text_xml_robust(args.items.read_bytes())
        values = Values(parse_text_xml_robust(args.values.read_bytes()))
        report = audit_equipment(SimpleNamespace(x1_values=lambda: values), items)
    except (OSError, ValueError, ET.ParseError) as e:
        parser.exit(2, f'Cannot read equipment inputs: {e}\n')
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        c = report['counts']
        print(f"{report['total']} equipment: {c['full']} full, {c['partial']} partial, {c['none']} none; "
              f"legacy converts {report['legacy_converts']}")
        print('Static analysis only. Full coverage may include approximations. No build files changed.')
        for item in report['items']:
            suffix = ' (approximate)' if item['approximate'] else ''
            print(f"{item['coverage']:7} {item['name']}{suffix}")
            for bonus in item['bonuses']:
                print(f"  {bonus['bonus']}: {bonus['status']}: {bonus['reason']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
