"""SPEC 29 damage / visual check with a VULNERABLE hero (no setInvulnerable at all): the fire wall harment in
haarp_ext01, then the flamer and the mp5 soldiers in haarp_ext04. Frames + the red health bar length per frame."""
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


def zone():
    try:
        return CZ.read_zone(PID)
    except Exception as e:      # noqa: BLE001
        return f'?{e}'


def wait_zone(name, timeout=90):
    t = time.time()
    while time.time() - t < timeout:
        if zone() == name:
            return True
        time.sleep(1)
    log(f'TIMEOUT waiting for {name}; zone is {zone()}')
    return False


def frames(label, n, gap=0.9):
    bars = []
    for i in range(n):
        p = os.path.join(OUT, f'{label}_{i:02d}.png'); F.screenshot(p); bars.append(redlen(p)); time.sleep(gap)
    log(f'{label}: bar {bars}')
    return bars


def goto(z):
    if zone() != z:
        F.script(f'loadMapKeepTeam("{z}")')
        if not wait_zone(z):
            sys.exit(3)
        time.sleep(6)


def heal():
    F.script('restoreHealth("_HERO1_",10000)')


steps = sys.argv[1:] or ['menu', 'wall', 'fire', 'sweep', 'range']
if 'menu' in steps:
    t = time.time()
    while not zone().startswith('menu') and time.time() - t < 120:
        time.sleep(2)
    log(f'zone {zone()}')
    time.sleep(3)
    F.key('RETURN'); time.sleep(2.5); F.key('RETURN')
    if not wait_zone('nyc/alison/nyc1_1_1'):
        sys.exit(2)
    time.sleep(8)
    F.script('setAutoSpend(1,1)'); F.script('awardXPToPlayable(600)'); time.sleep(1)
    heal()

if 'wall' in steps:
    goto('haarp/ext/haarp_ext01')
    frames('w_before', 2)
    F.script('copyOriginAndAngles("_HERO1_","fire_wall")'); time.sleep(2)
    frames('w_wall', 7)
    heal()
if 'fire' in steps:
    goto('haarp/ext/haarp_ext01')
    F.script('copyOriginAndAngles("_HERO1_","fire")'); time.sleep(2)
    frames('w_fire', 5)
    heal()
if 'sweep' in steps:
    goto('haarp/ext/haarp_ext04')
    F.script('copyOriginAndAngles("_HERO1_","flameguy_c")'); time.sleep(2)
    F.hold('s', 0.5); time.sleep(0.8)
    F.script('faceEntity("flameguy_c","_HERO1_")'); time.sleep(0.4)
    F.script('setCombatNode("flameguy_c","flame_sweep")'); F.script('loopCombatNode("flameguy_c","flame_sweep","LOOP_WAKE")')
    time.sleep(0.5)
    frames('s_sweep', 10, 0.8)
    F.script('setCombatNode("flameguy_c","idle")'); F.script('loopCombatNode("flameguy_c","","")')
    heal()
if 'range' in steps:
    goto('haarp/ext/haarp_ext04')
    F.script('copyOriginAndAngles("_HERO1_","generator_fence_ha03")'); time.sleep(2)
    frames('r_range', 14, 1.0)
    heal()
log('done')
