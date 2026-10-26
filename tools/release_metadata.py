"""Offline tag/version/notes policy shared by the release workflow and its tests."""
import argparse
import json
import re
from pathlib import Path

NUMBER = r'(?:0|[1-9][0-9]*)'
TAG = re.compile(rf'v(?P<base>{NUMBER}\.{NUMBER}\.{NUMBER})(?:-(?:beta|rc)\.{NUMBER})?')


def metadata(tag: str) -> dict:
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError(f'invalid release tag {tag!r}: expected vX.Y.Z[-beta.N|-rc.N]')
    pre = '-' in tag
    return dict(tag=tag, version=tag[1:], base=match['base'], prerelease=pre,
                flags=['--prerelease', '--latest=false'] if pre else [])


def release_version(tag: str | None, built: str) -> str:
    if not tag:
        return built
    meta = metadata(tag)
    if meta['base'] != metadata('v' + built)['base'] or ('-' in built and meta['version'] != built):
        raise ValueError(f'tag {tag}, but the builder is version {built}: update VERSION in tools/xml1builder/__init__.py')
    return meta['version']


def release_notes(tag: str, content: int, changelog: str, checksums: str) -> str:
    meta = metadata(tag)
    base_tag = 'v' + meta['base']
    section, active, found = [], False, False
    for line in changelog.splitlines():
        if line.startswith('## '):
            active = line == '## ' + base_tag or line.startswith('## ' + base_tag + ' ')
            found |= active
            continue
        if active:
            section.append(line)
    if meta['prerelease'] and not found:
        raise ValueError(f'CHANGELOG.md has no ## {base_tag} section')
    banner = 'Beta - test build\n\n' if meta['prerelease'] else ''
    # Keep the stable release's introduction, standalone instructions and checksum block.
    return (banner + f'Legends Classic builder {tag} (content version {content}).\n\n'
            + '\n'.join(section) + '\n\n'
            'The Ultimate Legends launcher installs and runs it for you. Standalone use: unzip, then run\n'
            '`xml1-builder.exe --help`. It contains no game data: it builds X-Men Legends from your own Xbox disc\n'
            'image and your own X-Men Legends II install, and makes no network calls.\n\n'
            'SHA-256:\n```\n' + checksums.rstrip('\n') + '\n```\n')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tag', required=True)
    ap.add_argument('--notes-output', type=Path)
    ap.add_argument('--changelog', type=Path, default=Path('CHANGELOG.md'))
    ap.add_argument('--dist', type=Path, default=Path('dist'))
    args = ap.parse_args()
    try:
        meta = metadata(args.tag)
        if args.notes_output:
            manifest = json.loads((args.dist / 'xml1-builder.json').read_text(encoding='utf-8'))
            if manifest['version'] != meta['version']:
                raise ValueError('release manifest version differs from the tag')
            notes = release_notes(args.tag, manifest['content_version'], args.changelog.read_text(encoding='utf-8'),
                                  (args.dist / 'SHA256SUMS.txt').read_text(encoding='utf-8'))
            args.notes_output.write_text(notes, encoding='utf-8', newline='\n')
    except (ValueError, KeyError, OSError) as exc:
        ap.error(str(exc))
    print(json.dumps(meta))


if __name__ == '__main__':
    main()
