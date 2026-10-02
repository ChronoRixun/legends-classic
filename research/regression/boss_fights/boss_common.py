"""Shared helpers for the boss-fight drivers (research/audit/boss_fights_2026-10-01.md).

Binds fixinput / current_zone to one build (default build/_t16, pipe "boss"), writes frames to the session
scratchpad (never into the repo), measures the boss bar and the party's health bars off the frames, and wraps
the pipe's one-line script verb (statements joined with the four characters backslash-n backslash-r).
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os
import tempfile
import sys
import time

sys.path.insert(0, _REPO + '/tools')
import fixinput as F          # noqa: E402
import current_zone as CZ     # noqa: E402
from PIL import Image         # noqa: E402

BUILD = os.environ.get('BOSS_BUILD', _REPO + '/build/_t16')
OUT = os.environ.get('BOSS_OUT', os.path.join(tempfile.gettempdir(), 'xml1-boss-shots'))
os.makedirs(OUT, exist_ok=True)
T0 = time.time()
LOGFILE = None


def log(m):
    line = f'[{time.time() - T0:6.1f}s] {m}'
    print(line, flush=True)
    if LOGFILE:
        with open(LOGFILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


F.use_build(BUILD)
PID = CZ.game_pid(BUILD)


def zone():
    try:
        return CZ.read_zone(PID)
    except Exception as e:      # noqa: BLE001
        return f'?{e}'


def wait_zone(name, timeout=120):
    t = time.time()
    while time.time() - t < timeout:
        z = zone()
        if z == name:
            return True
        time.sleep(1)
    log(f'TIMEOUT waiting for {name}; zone is {zone()}')
    return False


def script(*statements):
    """One pipe line: statements joined with backslash-n backslash-r (the fix splits them)."""
    line = r'\n\r'.join(statements)
    return F.script(line)


def shot(label):
    p = os.path.join(OUT, f'{label}.png')
    F.screenshot(p)
    return p


# --- frame measurements -------------------------------------------------------------------------------------
# Calibrated on the 1280x720 windowed frames of this harness (see boss_common.calibrate()).
BOSSBAR_Y = None   # set by calibrate() / the driver once the first boss frame is seen
BOSSBAR_X = (0, 1280)


def red_run(im, y, x0, x1):
    """Longest run of 'health red' pixels on row y between x0 and x1 (the HUD bars are solid red)."""
    best = cur = 0
    for x in range(x0, x1):
        r, g, b = im.getpixel((x, y))
        if r > 150 and g < 90 and b < 90:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def red_rows(path, x0=0, x1=1280, y0=0, y1=720, min_run=20):
    """Every row with a red run of at least min_run pixels: (y, run). Used to locate the boss bar."""
    im = Image.open(path).convert('RGB')
    out = []
    for y in range(y0, y1):
        r = red_run(im, y, x0, x1)
        if r >= min_run:
            out.append((y, r))
    return out


def bossbar(path, y=72, x0=449, x1=860, full=403):
    """Percent of the boss bar (top-centre HUD bar, drawn (127,25,25) on row 72, x 449..851 when full)."""
    im = Image.open(path).convert('RGB')
    last = None
    for x in range(x0, x1):
        r, g, b = im.getpixel((x, y))
        if 100 <= r <= 140 and g < 45 and b < 45:
            last = x
    if last is None:
        return None
    return round(100.0 * (last - x0 + 1) / full, 1)


def frames(label, n, gap=1.0, measure=True):
    out = []
    for i in range(n):
        p = shot(f'{label}_{i:02d}')
        out.append((p, bossbar(p) if measure else None))
        time.sleep(gap)
    if measure:
        load_refs()
        log(f'{label}: bossbar {[b for _, b in out]} titles {[title_match(p)[0] for p, _ in out]}')
    return out


# --- game flow ----------------------------------------------------------------------------------------------
def new_game(xp=2000000, timeout=150):
    """From the XML1 main menu: Begin Story (RETURN, RETURN) -> nyc1_1_1; then level the roster."""
    t = time.time()
    while not zone().startswith('menu') and time.time() - t < 120:
        time.sleep(2)
    log(f'zone {zone()}')
    time.sleep(3)
    F.key('RETURN'); time.sleep(2.5); F.key('RETURN')
    if not wait_zone('nyc/alison/nyc1_1_1', timeout):
        sys.exit(2)
    time.sleep(8)
    script('setAutoSpend(1,1)', f'awardXPToPlayable({xp})')
    time.sleep(1)


def seat(*heroes):
    h = list(heroes) + [''] * (4 - len(heroes))
    script('seatParty("%s","%s","%s","%s")' % tuple(h))


def goto(z, settle=8, timeout=120):
    if zone() != z:
        F.script(f'loadMapKeepTeam("{z}")')
        if not wait_zone(z, timeout):
            sys.exit(3)
        time.sleep(settle)


def invulnerable(on=True):
    v = 'TRUE' if on else 'FALSE'
    script(*[f'setInvulnerable("_HERO{i}_","{v}")' for i in (1, 2)])
    script(*[f'setInvulnerable("_HERO{i}_","{v}")' for i in (3, 4)])


def heal():
    script(*[f'restoreHealth("_HERO{i}_",10000)' for i in (1, 2)])
    script(*[f'restoreHealth("_HERO{i}_",10000)' for i in (3, 4)])


def teleport_party_to(entity):
    script(*[f'copyOriginAndAngles("_HERO{i}_","{entity}")' for i in (1, 2)])
    script(*[f'copyOriginAndAngles("_HERO{i}_","{entity}")' for i in (3, 4)])


def fraction(boss, frac):
    """Set a boss's health to a fraction of its max (pain scripts fire on the next hit, not on setHealth)."""
    script(f'h=getHealthMax("{boss}")', f'h=fmul(h,{frac:.3f})', f'setHealth("{boss}",h)')


def attack_burst(key='NUMPAD6', n=6, gap=0.35):
    for _ in range(n):
        F.key(key)
        time.sleep(gap)


def dismiss(n=3):
    for _ in range(n):
        F.key('RETURN'); time.sleep(0.6)


# --- liveness --------------------------------------------------------------------------------------------
import ctypes                      # noqa: E402
import ctypes.wintypes as _w       # noqa: E402


def game_hwnd():
    u = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, _w.HWND, _w.LPARAM)
    def cb(h, _):
        p = _w.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == PID and u.IsWindowVisible(h):
            found.append(h)
        return True
    u.EnumWindows(cb, 0)
    return found[0] if found else None


def responding(timeout_ms=2000):
    """False when the game's window thread no longer pumps messages (a hang), like Task Manager's column."""
    h = game_hwnd()
    if not h:
        return None
    u = ctypes.windll.user32
    res = ctypes.c_ulong()
    ok = u.SendMessageTimeoutW(h, 0, 0, 0, 0x0002 | 0x0008, timeout_ms, ctypes.byref(res))  # SMTO_ABORTIFHUNG|NOTIMEOUTIFNOTHUNG
    return bool(ok)


def safe_shot(label, tries=3):
    for i in range(tries):
        try:
            return shot(label)
        except Exception as e:      # noqa: BLE001
            log(f'shot {label}: {e}; responding={responding()}')
            time.sleep(2)
    return None


# --- boss-bar title (which enemy the bar shows) --------------------------------------------------------------
TITLE_BOX = (520, 76, 780, 92)
_REFS = {}


def title_sig(path):
    im = Image.open(path).convert('L').crop(TITLE_BOX)
    return [255 if p > 170 else 0 for p in im.getdata()]   # the white title text only, not the bar under it


def title_ref(name, path):
    _REFS[name] = title_sig(path)


def title_match(path, cutoff=18.0):
    """Nearest stored reference by mean abs difference of the title band; '?' when nothing is close."""
    s = title_sig(path)
    best, bd = '?', 1e9
    for n, r in _REFS.items():
        d = sum(abs(a - b) for a, b in zip(s, r)) / len(s)
        if d < bd:
            best, bd = n, d
    return (best if bd < cutoff else '?'), round(bd, 1)


REF_FRAMES = {'magneto': '21_mag_conv_07', 'acolyte_master': '22_mag_fight_00', 'acolyte_elite': '23_mag_stage2_00',
              'mastermold': '41_mm_watch_00'}


def load_refs():
    for n, f in REF_FRAMES.items():
        p = os.path.join(OUT, f + '.png')
        if n not in _REFS and os.path.exists(p):
            title_ref(n, p)


def fresh_to(z, heroes=('wolverine', 'cyclops', 'storm', 'iceman'), settle=20):
    """New game from the menu (skipped when a game is already loaded), seat the party, load the boss zone,
    wait, check the window still responds."""
    if zone().startswith('menu'):
        new_game()
    seat(*heroes)
    time.sleep(1)
    F.script(f'loadMapKeepTeam("{z}")')
    if not wait_zone(z, 120):
        sys.exit(3)
    for i in range(settle // 2):
        time.sleep(2)
        if responding() is False:
            log(f'HUNG {i * 2} s after the load of {z}')
            return False
    invulnerable(True)
    time.sleep(1)
    log(f'zone {zone()} responding {responding()}')
    return True
