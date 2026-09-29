"""Test helper: make every tour wrapper script show its stop number and zone name via hudMessage.

usage: tour_label.py <tour_build_dir> [<int_arg> <seconds>]
"""
import os, re, sys

build = sys.argv[1]
kind = sys.argv[2] if len(sys.argv) > 2 else '0'
secs = sys.argv[3] if len(sys.argv) > 3 else '11.0'
root = os.path.join(build, 'Scripts', 'x1', 'tour')
n = 0
for d, _, files in os.walk(root):
    for f in files:
        if not f.endswith('.py'):
            continue
        p = os.path.join(d, f)
        lines = open(p, 'rb').read().decode('latin-1').split('\r\n')
        lines = [l for l in lines if not l.startswith('hudMessage(')]
        m = re.match(r'# xml1-port tour stop (\d+)/\d+: (\S+)', lines[0])
        if not m:
            continue
        label = f'TOUR{int(m.group(1)):03d}_{m.group(2)}'
        lines.insert(1, f'hudMessage({kind}, {secs}, "{label}" )')
        open(p, 'wb').write('\r\n'.join(lines).encode('latin-1'))
        n += 1
print('labelled', n, 'tour scripts')
