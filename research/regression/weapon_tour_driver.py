"""SPEC 29 in-game check: one zone per XML1 weapon type, an invulnerable Wolverine standing in it, frames while the
soldiers fire (build/_wpn, pipe wpn). Zones: spawners with instantspawn="true" for that weapon's soldiers."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, time
sys.path.insert(0, _REPO + '/tools')
import fixinput as F          # noqa: E402
import current_zone as CZ     # noqa: E402

BUILD = _REPO + '/build/_wpn'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wpn')
os.makedirs(OUT, exist_ok=True)
T0 = time.time()
ZONES = [  # (label, zone, spawner to stand next to (a dormant one stays in the world), seconds to watch)
    ('flame', 'haarp/ext/haarp_ext04', 'ss_haarpsoldier_flamethrower02', 16),
    ('lightning', 'sewers/grso/sewers3_1_2', 'ss_grso_commander02', 14),
    ('freeze', 'haarp/int/haarp2_1', 'ss_haarpleader01', 14),
    ('knockback', 'demo/a_int/arb3_2', 'ss_grso_captain01', 14),
    ('laser', 'hive/h_ext/hive1_1_1', '2sw1', 14),
]


def log(m):
    print(f'[{time.time() - T0:6.1f}s] {m}', flush=True)


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


def shot(n):
    p = os.path.join(OUT, n + '.png'); F.screenshot(p); log(f'shot {n}'); return p


only = sys.argv[1:]
if zone().startswith('menu'):
    F.key('RETURN'); time.sleep(2.5); F.key('RETURN')
    if not wait_zone('nyc/alison/nyc1_1_1'):
        sys.exit(2)
    time.sleep(8)
F.script(r'setInvulnerable("_HERO1_","TRUE")')
last = None
for label, z, sp, secs in ZONES:
    if only and label not in only:
        continue
    if z != last:
        F.script(f'loadMapKeepTeam("{z}")')
        if not wait_zone(z):
            continue
        time.sleep(6)
        last = z
    F.script(f'copyOriginAndAngles("_HERO1_","{sp}")'); time.sleep(2.5); shot(f'{label}_00')
    for i in range(1, int(secs / 1.5) + 1):
        time.sleep(1.5); shot(f'{label}_{i:02d}')
    log(f'{label} done ({z} @ {sp})')
log('done')
