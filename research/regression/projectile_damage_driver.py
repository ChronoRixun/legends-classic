"""0.1.4 play check (PR #1: entity value codes resolved): a VULNERABLE hero next to a dormant spawner that is acted
-> freeze gun (ice_bullet), knockback gun (bullet_time), grenades; the health bar per frame + frames.
usage: wpn_drive4.py <build> [labels...]"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, time
sys.path.insert(0, _REPO + '/tools')
import fixinput as F, current_zone as CZ      # noqa: E402
from PIL import Image                          # noqa: E402

B = sys.argv[1]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'w4'); os.makedirs(OUT, exist_ok=True)
T0 = time.time()
TESTS = [  # label, zone, spawner to stand on and act (dormant), frames
    ('freeze', 'haarp/int/haarp2_2', 'ss_haarpleader02', 30),
    ('knockback', 'demo/a_int/arb3_1', 'ss_grso_captain01', 30),
    ('grenade', 'haarp/ext/haarp_ext04', 'generator_fence_ha03', 30),       # instantspawn mp5 soldiers throw grenades
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


def hud_visible():
    p = os.path.join(OUT, 'chk.png'); F.screenshot(p); return redlen(p) > 0


only = sys.argv[2:]
t = time.time()
while not z().startswith('menu') and time.time() - t < 150:
    time.sleep(2)
time.sleep(3); F.key('RETURN'); time.sleep(2.5); F.key('RETURN')
log(f'nyc {wait("nyc/alison/nyc1_1_1")}'); time.sleep(8)
F.script('setAutoSpend(1,1)'); F.script('awardXPToPlayable(2000)'); time.sleep(1)
for label, zone, sp, n in TESTS:
    if only and label not in only:
        continue
    F.script(f'loadMapKeepTeam("{zone}")')
    if not wait(zone):
        log(f'{label}: TIMEOUT {z()}'); continue
    time.sleep(7)
    F.script('restoreHealth("_HERO1_",10000)')
    F.script(f'copyOriginAndAngles("_HERO1_","{sp}")'); time.sleep(1.0)
    for i in range(4):                       # dialogs at the zone start: RETURN until the HUD shows
        if hud_visible():
            break
        F.key('RETURN'); time.sleep(1.5)
    if sp.startswith('ss_'):
        F.script(f'act("{sp}","{sp}")'); time.sleep(1.0)
    bars = []
    for i in range(n):
        if i % 8 == 0:
            F.script('restoreHealth("_HERO1_",10000)')
        p = os.path.join(OUT, f'{label}_{i:02d}.png'); F.screenshot(p); bars.append(redlen(p)); time.sleep(0.5)
    log(f'{label}: bar {bars}')
    F.script('restoreHealth("_HERO1_",10000)')
    ims = [Image.open(os.path.join(OUT, f'{label}_{i:02d}.png')) for i in (2, 7, 12, 17, 22, 27)]
    S = Image.new('RGB', (1280, 1080))
    for k, im in enumerate(ims):
        S.paste(im.resize((640, 360)), ((k % 2) * 640, (k // 2) * 360))
    S.save(os.path.join(OUT, f'sheet_{label}.png'))
log('done')
