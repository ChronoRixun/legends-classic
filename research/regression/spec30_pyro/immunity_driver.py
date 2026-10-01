"""SPEC 30 in-game check (research/regression/spec30_pyro): Pyro with his AI off (setAIActive, XMen2.exe 0x4a50f0) teleported onto Wolverine before
every smash; frames 0.15 / 0.3 / 0.5 / 0.8 s after the key, centre crops. usage: imm_driver3.py <build> <tag>."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, time
sys.path.insert(0, _REPO + '/tools')
import fixinput as F          # noqa: E402
import current_zone as CZ     # noqa: E402
from PIL import Image         # noqa: E402

BUILD = os.path.abspath(sys.argv[1])
TAG = sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots', TAG)
os.makedirs(OUT, exist_ok=True)
T0 = time.time()
ZONE, SPAWNER, MONSTER = 'haarp/int/haarp2_6', 'sp_pyroact01', 'pyro'
SMASH = 'NUMPAD6'
N = 10
DELAYS = (0.15, 0.3, 0.5, 0.8)


def log(m):
    print(f'[{time.time() - T0:6.1f}s] {m}', flush=True)


import subprocess
if 'nolaunch' not in sys.argv and CZ.game_pid(BUILD) is None:
    subprocess.Popen([sys.executable, _REPO + '/tools/gamedbg.py', os.path.join(BUILD, 'dbg.log'),
                      os.path.join(BUILD, 'XMen2.exe')],
                     stdout=open(os.path.join(OUT, 'gamedbg.out'), 'w'), stderr=subprocess.STDOUT,
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
    log('launched')
F.use_build(BUILD)
t = time.time()
while CZ.game_pid(BUILD) is None and time.time() - t < 60:
    time.sleep(1)
PID = CZ.game_pid(BUILD)
log(f'pid {PID}')
while not F.check(verbose=False) and time.time() - t < 150:
    time.sleep(2)
log(f'pipe up {F.check(verbose=False)}')


def z():
    return CZ.read_zone(PID) or ''


def wait(zone, limit=150):
    t = time.time()
    while z() != zone and time.time() - t < limit:
        time.sleep(1)
    return z() == zone


def shot(n):
    p = os.path.join(OUT, f'{n}.png')
    F.screenshot(p)
    return p


if True:
    t = time.time()
    while not z().startswith('menu') and time.time() - t < 150:
        time.sleep(2)
    log(f'menu: {z()}')
    time.sleep(3); F.key('RETURN'); time.sleep(2.5); F.key('RETURN')
    log(f'nyc {wait("nyc/alison/nyc1_1_1")}'); time.sleep(8)
    F.script('setAutoSpend(1,1)'); F.script('awardXPToPlayable(2000)'); time.sleep(1)

F.script(r'seatParty("wolverine","colossus","cyclops","iceman")\n\rloadMapKeepTeam("%s")' % ZONE)
time.sleep(2)
log(f'{ZONE} {wait(ZONE)}'); time.sleep(7)
for i in range(3):
    F.key('RETURN'); time.sleep(1.2)
F.script('restoreHealth("_HERO1_",10000)')
F.script(f'act("{SPAWNER}","{SPAWNER}")'); time.sleep(3.0)
for i in range(4):
    F.key('RETURN'); time.sleep(1.0)
F.script(f'setAIActive("{MONSTER}","FALSE")'); time.sleep(0.5)
shot('00_spawned')
frames = []
for i in range(N):
    F.script('restoreHealth("_HERO1_",10000)')
    F.script(f'copyOriginAndAngles("{MONSTER}","_HERO1_")'); time.sleep(0.5)
    shot(f'10_smash_{i:02d}_pre'); frames.append(f'10_smash_{i:02d}_pre')
    F.key(SMASH)
    t = time.time()
    for j, d in enumerate(DELAYS):
        while time.time() - t < d:
            time.sleep(0.01)
        shot(f'10_smash_{i:02d}_{j}'); frames.append(f'10_smash_{i:02d}_{j}')
    F.key('RETURN'); time.sleep(0.5)
shot('30_end')
log('shots done')
cols = 5
rows = (len(frames) + cols - 1) // cols
S = Image.new('RGB', (cols * 480, rows * 270))
for k, n in enumerate(frames):
    im = Image.open(os.path.join(OUT, f'{n}.png'))
    w, h = im.size
    crop = im.crop((w // 2 - 160, h // 2 - 90, w // 2 + 160, h // 2 + 90)).resize((480, 270), Image.LANCZOS)
    S.paste(crop, ((k % cols) * 480, (k // cols) * 270))
S.save(os.path.join(OUT, 'sheet_centre.png'))
log(f'done zone={z()}')
