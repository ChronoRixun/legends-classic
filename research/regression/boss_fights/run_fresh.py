"""Run one boss driver in a fresh game process: kill the build's game if it runs, launch it under
tools/gamedbg.py (detached), wait for the main menu, then run the driver (whose 'load' step does the New Game).
usage: run_fresh.py <driver.py> [driver args...]
Why: three of three cross-zone loadMapKeepTeam loads out of a finished / running boss fight stopped the game
from presenting frames (then the window stopped responding); loads from a fresh game were fine."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os
import tempfile, subprocess, sys, time

sys.path.insert(0, _REPO + '/tools')
import current_zone as CZ   # noqa: E402

BUILD = os.environ.get('BOSS_BUILD', _REPO + '/build/_t16')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get('BOSS_OUT', os.path.join(tempfile.gettempdir(), 'xml1-boss'))

if CZ.game_pid(BUILD):
    print('killing', CZ.kill_build(BUILD), flush=True)
    time.sleep(2)
log = open(os.path.join(OUT, 'gamedbg_%s.txt' % time.strftime('%H%M%S')), 'w')
subprocess.Popen([sys.executable, _REPO + '/tools/gamedbg.py', BUILD + '/dbg.log', BUILD + '/XMen2.exe'],
                 stdout=log, stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | NEW_PROCESS_GROUP
t = time.time()
pid = None
while time.time() - t < 90:
    pid = CZ.game_pid(BUILD)
    if pid:
        try:
            if CZ.read_zone(pid).startswith('menu'):
                break
        except Exception:   # noqa: BLE001
            pass
    time.sleep(2)
print('game', pid, 'zone', CZ.read_zone(pid) if pid else None, flush=True)
time.sleep(3)
sys.exit(subprocess.call([sys.executable, os.path.join(HERE, sys.argv[1])] + sys.argv[2:]))
