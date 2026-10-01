"""SPEC 29: every XML1 weapon type in game with a VULNERABLE hero: stand on a dormant spawner, act it, watch the
health bar and the frames. Also the fire_wall harm entity of haarp_ext01 (Owen's 'invisible flame')."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, time
sys.path.insert(0, _REPO + '/tools')
import fixinput as F          # noqa: E402
import current_zone as CZ     # noqa: E402
from PIL import Image         # noqa: E402

BUILD = _REPO + '/build/_wpn'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wpn')
T0 = time.time()
# label, zone, spawner (dormant: still in the world), dismiss-dialog RETURN first?
TESTS = [
    ('mp5', 'haarp/ext/haarp_ext04', 'generator_fence_ha03', False),      # instantspawn mp5 soldiers next to it
    ('wall', 'haarp/ext/haarp_ext01', 'fire_wall', True),
    ('freeze', 'haarp/int/haarp2_1', 'ss_haarpleader01', False),
    ('lightning', 'sewers/grso/sewers3_1_2', 'ss_grso_commander02', False),
    ('knockback', 'demo/a_int/arb3_2', 'ss_grso_captain01', False),
    ('laser', 'hive/h_ext/hive1_1_1', '2sw1', True),
]


def log(m):
    print(f'[{time.time() - T0:6.1f}s] {m}', flush=True)


def redlen(p):
    im = Image.open(p).convert('RGB'); y = 627; n = 0
    for x in range(190, 400):
        r, g, b = im.getpixel((x, y))
        if r > 200 and g < 110 and b < 60:
            n += 1
    return n


F.use_build(BUILD)
PID = CZ.game_pid(BUILD)


def goto(z):
    if CZ.read_zone(PID) == z:
        return True
    F.script(f'loadMapKeepTeam("{z}")'); t = time.time()
    while CZ.read_zone(PID) != z and time.time() - t < 90:
        time.sleep(1)
    if CZ.read_zone(PID) != z:
        log(f'TIMEOUT {z}: {CZ.read_zone(PID)}'); return False
    time.sleep(7)
    return True


only = sys.argv[1:]
for label, z, sp, dialog in TESTS:
    if only and label not in only:
        continue
    if not goto(z):
        continue
    F.script('restoreHealth("_HERO1_",10000)')
    F.script(f'copyOriginAndAngles("_HERO1_","{sp}")'); time.sleep(1.0)
    if dialog:
        F.key('RETURN'); time.sleep(2.0)
    if sp.startswith('ss_') or sp == '2sw1':
        F.script(f'act("{sp}","{sp}")'); time.sleep(1.0)
    bars = []
    for i in range(24):
        if i % 4 == 0:
            F.script('restoreHealth("_HERO1_",10000)')          # stay alive: a death ends the run in a menu
        p = os.path.join(OUT, f'{label}_{i:02d}.png'); F.screenshot(p); bars.append(redlen(p)); time.sleep(0.5)
    log(f'{label}: bar {bars}')
    F.script('restoreHealth("_HERO1_",10000)')
    ims = [Image.open(os.path.join(OUT, f'{label}_{i:02d}.png')) for i in (2, 6, 10, 14, 18, 22)]
    S = Image.new('RGB', (1280, 1080))
    for k, im in enumerate(ims):
        S.paste(im.resize((640, 360)), ((k % 2) * 640, (k // 2) * 360))
    S.save(os.path.join(OUT, f'sheet_{label}.png'))
log('done')
