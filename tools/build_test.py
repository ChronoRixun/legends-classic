"""Rebuild the XML2 test copy from the real install, then convert XML1 zones into it.

usage: build_test.py <start_zone> [<extra_zone> ...] [--overlay <dir>] ...

Test-only tweaks: windowed mode, engine reporting on, no movies, and a new game jumps
straight to <start_zone> via the tutorial's zone script. Each --overlay directory mirrors
the install root and is copied on top after conversion (e.g. research prototype outputs).
The xml2-fix proxy (dinput.dll, mods/, xml2-fix.*) is left out so tests see stock XML2.
"""
import os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_paths  # noqa: E402
XML2 = local_paths.xml2_dir()
TEST = os.path.join(ROOT, 'xml2_test')
X1 = os.path.join(ROOT, 'xml1_loose')
TOOLS = os.path.join(ROOT, 'tools')


def overlay(src):
    """Copy src over TEST, reusing the existing spelling of any path that differs only in case."""
    for d, _, files in os.walk(src):
        rel_dir = os.path.relpath(d, src)
        for f in files:
            if f.startswith('_'):
                continue
            rel = os.path.normpath(os.path.join(rel_dir, f))
            dst = TEST
            for part in rel.split(os.sep):
                match = next((e for e in os.listdir(dst) if e.lower() == part.lower()), None) \
                    if os.path.isdir(dst) else None
                dst = os.path.join(dst, match or part)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(d, f), dst)


def main(zones, overlays):
    if os.path.exists(TEST):
        shutil.rmtree(TEST)
    shutil.copytree(XML2, TEST, ignore=shutil.ignore_patterns(
        '*.sfd', 'dinput.dll', 'xml2-fix.*', 'mods'))

    ini = os.path.join(TEST, 'alchemy.ini')
    text = open(ini, encoding='latin-1').read()
    text = text.replace('fullScreen = true', 'fullScreen = false')
    text = text.replace('defaultReportLevel = kNone', 'defaultReportLevel = kInfo')
    open(ini, 'w', encoding='latin-1', newline='').write(text)

    script = os.path.join(TEST, 'Scripts', 'act0', 'tutorial', 'tutorial1', 'tutorial1.py')
    body = open(script, 'rb').read()
    jump = (f'# xml1-port test: jump straight to the converted zone\r\n'
            f'waittimed ( 1.000 )\r\nloadZone("{zones[0]}", "" )\r\n').encode()
    open(script, 'wb').write(jump + body)

    manifest = os.path.join(ROOT, '.codegpt-game.json')
    if os.path.exists(manifest):
        shutil.copy(manifest, TEST)
    subprocess.run([sys.executable, os.path.join(TOOLS, 'convert_zone.py'), X1, TEST, *zones], check=True)
    for o in overlays:
        overlay(o)
        print('overlay', o)


if __name__ == '__main__':
    args = sys.argv[1:]
    zones, overlays = [], []
    while args:
        a = args.pop(0)
        if a == '--overlay':
            overlays.append(args.pop(0))
        else:
            zones.append(a)
    main(zones, overlays)
