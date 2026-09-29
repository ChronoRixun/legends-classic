r"""Drive ONLY the build\_skins game window (pipe skins) - never the other agent's windows.

usage: late.py pid | zone | conv | xp | party | log [N] | shot NAME | key K [n] | hold K ms | script STMT |
               console CMD | status | talk [secs] | wait_zone ZONE [secs] | launch | kill | state
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json
import os
import re
import subprocess
import sys
import time

os.environ['XML2FIX_PIPE'] = 'skins'
TOOLS = _REPO + r'\tools'
sys.path.insert(0, TOOLS)
import current_zone  # noqa: E402
import conv_probe  # noqa: E402
import fixinput  # noqa: E402
import hero_xp  # noqa: E402

BUILD = _REPO + r'\build\_skins'
EXE = os.path.join(BUILD, 'XMen2.exe')
LOG = os.path.join(BUILD, 'xml2-fix.log')
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots')
os.makedirs(SHOTS, exist_ok=True)


def my_pid():
    ps = ('Get-CimInstance Win32_Process -Filter "Name=\'XMen2.exe\'" | '
          'ForEach-Object { "$($_.ProcessId)|$($_.ExecutablePath)" }')
    out = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if '|' in line:
            pid, path = line.strip().split('|', 1)
            if os.path.normcase(os.path.abspath(path)) == os.path.normcase(EXE):
                return int(pid)
    return None


_PID = None


def pid():
    global _PID
    if _PID is None:
        _PID = my_pid()
    return _PID


# every tool that looks for "the" game gets ours
current_zone.game_pid = pid
hero_xp.game_pid = pid


def zone():
    p = pid()
    return current_zone.read_zone(p) if p else None


def conv():
    p = pid()
    return conv_probe.probe(p) if p else {}


def ask(line):
    return fixinput.pipe().ask(line)


def shot(name):
    path = os.path.join(SHOTS, name if name.endswith('.png') else name + '.png')
    ask(f'screenshot {path}')
    return path


def log_size():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def log_from(start):
    with open(LOG, 'rb') as f:
        f.seek(start)
        return f.read().decode('utf-8', 'replace')


def talk(limit=120, gap=1.3):
    """Click through conversations until none has been active for 3 s."""
    t0 = time.time()
    idle = None
    same, last, presses = 0, None, 0
    while time.time() - t0 < limit:
        c = conv()
        if c.get('active'):
            idle = None
            line = c.get('line_id')
            same = same + 1 if line == last else 0
            last = line
            sel, cnt = c.get('selected'), c.get('visible_responses')
            if isinstance(sel, int) and isinstance(cnt, int) and cnt > 0 and sel >= cnt:
                ask('tap DOWN 120')
                time.sleep(0.4)
            elif same >= 3:
                ask('tap DOWN 120')
                same = 0
                time.sleep(0.4)
            ask('tap RETURN 120')
            presses += 1
            time.sleep(gap)
            continue
        idle = idle or time.time()
        if time.time() - idle > 3:
            break
        time.sleep(0.25)
    return presses


def wait_zone(target, limit=240):
    t0 = time.time()
    while time.time() - t0 < limit:
        z = (zone() or '').lower()
        if z == target.lower():
            return round(time.time() - t0, 1)
        time.sleep(0.5)
    return None


def party():
    start = log_size()
    stmt = r'\n\r'.join(f'getPartyMember({i})' for i in range(4))
    ask(f'script {stmt}')
    got = {}
    for _ in range(20):
        time.sleep(0.5)
        for m in re.finditer(r'getPartyMember\((\d)\) -> "([^"]*)"', log_from(start)):
            got[int(m.group(1))] = m.group(2)
        if len(got) == 4:
            break
    return [got.get(i) for i in range(4)]


def main(argv):
    cmd = argv[0]
    if cmd == 'pid':
        print(pid())
    elif cmd == 'zone':
        print(zone())
    elif cmd == 'conv':
        print(json.dumps(conv()))
    elif cmd == 'xp':
        for name, level, xp, exempt in hero_xp.heroes(pid()):
            print(f'{name:16} level {level:3}  xp {xp if xp is not None else "-":>11}{"  (xpexempt)" if exempt else ""}')
    elif cmd == 'party':
        print(party())
    elif cmd == 'log':
        n = int(argv[1]) if len(argv) > 1 else 30
        with open(LOG, encoding='utf-8', errors='replace') as f:
            print(''.join(f.readlines()[-n:]))
    elif cmd == 'shot':
        print(shot(argv[1]))
    elif cmd == 'key':
        for _ in range(int(argv[2]) if len(argv) > 2 else 1):
            print(ask(f'tap {fixinput.dik(argv[1])} 120'))
            time.sleep(0.25)
    elif cmd == 'hold':
        print(ask(f'hold {argv[1]} {argv[2]}'))
    elif cmd == 'script':
        print(fixinput.script(' '.join(argv[1:])))
    elif cmd == 'console':
        print(fixinput.console(' '.join(argv[1:])))
    elif cmd == 'status':
        print(ask('status'))
    elif cmd == 'talk':
        print('presses', talk(float(argv[1]) if len(argv) > 1 else 120))
    elif cmd == 'wait_zone':
        print(wait_zone(argv[1], float(argv[2]) if len(argv) > 2 else 240))
    elif cmd == 'state':
        c = conv()
        print(json.dumps({'pid': pid(), 'zone': zone(), 'conv_active': c.get('active'), 'line': c.get('line_id'),
                          'sel': c.get('selected'), 'n': c.get('visible_responses')}))
    elif cmd == 'launch':
        if pid():
            sys.exit(f'already running: {pid()}')
        subprocess.run(['cmd', '/c', 'start', '', 'XMen2.exe'], cwd=BUILD)
        print('launched')
    elif cmd == 'kill':
        p = pid()
        if p:
            subprocess.run(['taskkill', '/PID', str(p), '/F'])
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
