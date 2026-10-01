"""Four-seat power-wheel check: new game, seatParty(4), loadMapKeepTeam(zone), dismiss dialogs, then for each seat
(UP RIGHT DOWN LEFT) hold the power key and capture the wheel. usage: wheel_seats.py <build> <tag> [zone] [h1,h2,h3,h4]"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, time
sys.path.insert(0, _REPO + '/tools')
import fixinput as F, current_zone as CZ      # noqa: E402
from PIL import Image                          # noqa: E402

B = sys.argv[1]; TAG = sys.argv[2]
ZONE = sys.argv[3] if len(sys.argv) > 3 else 'haarp/ext/haarp_ext01'
HEROES = (sys.argv[4] if len(sys.argv) > 4 else 'magma,phoenix,iceman,wolverine').split(',')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wheel'); os.makedirs(OUT, exist_ok=True)
F.use_build(B); PID = CZ.game_pid(B)


def z():
    try:
        return CZ.read_zone(PID)
    except Exception:       # noqa: BLE001
        return '?'


def wait(name, t=120):
    t0 = time.time()
    while z() != name and time.time() - t0 < t:
        time.sleep(1)
    return z() == name


def seats(tag):
    frames = []
    for key in ('UP', 'RIGHT', 'DOWN', 'LEFT'):
        F.key(key); time.sleep(1.5)
        F.down(['NUMPAD5']); time.sleep(1.0); F.screenshot(os.path.join(OUT, f'{tag}_{key}.png')); F.up(['NUMPAD5']); time.sleep(0.8)
        frames.append(f'{tag}_{key}')
    S = Image.new('RGB', (1280, 720))
    for k, n in enumerate(frames):
        im = Image.open(os.path.join(OUT, f'{n}.png'))
        tile = Image.new('RGB', (640, 360)); tile.paste(im.crop((0, 0, 400, 260)), (0, 0)); tile.paste(im.crop((0, 520, 400, 720)), (240, 160))
        S.paste(tile, ((k % 2) * 640, (k // 2) * 360))
    S.save(os.path.join(OUT, f'sheet_{tag}.png'))


if 'nomenu' not in sys.argv:
    t0 = time.time()
    while not z().startswith('menu') and time.time() - t0 < 150:
        time.sleep(2)
    time.sleep(3); F.key('RETURN'); time.sleep(2.5); F.key('RETURN')
    print('nyc', wait('nyc/alison/nyc1_1_1')); time.sleep(8)
    F.script('setAutoSpend(1,1)'); F.script('awardXPToPlayable(2000)'); time.sleep(1)
F.script(r'seatParty("%s","%s","%s","%s")\n\rloadMapKeepTeam("%s")' % (*HEROES, ZONE))
print(ZONE, wait(ZONE)); time.sleep(7)
for i in range(3):
    F.key('RETURN'); time.sleep(1.5)
F.script('awardXPToPlayable(2000)'); time.sleep(1)
seats(TAG)
print('done', z())
