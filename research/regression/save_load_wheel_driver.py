"""SPEC 28 in-game check: Cyclops's wheel after a save + load in nyc1_1_3 (build/_pwr, pipe pwr)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import glob, os, sys, time
sys.path.insert(0, _REPO + '/tools')
import fixinput as F          # noqa: E402
import current_zone as CZ     # noqa: E402

BUILD = _REPO + '/build/_pwr'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pwr')
SAVES = os.path.expanduser('~/Documents/Activision/X-Men Legends (pwr tests)/Save')
os.makedirs(OUT, exist_ok=True)
T0 = time.time()


def log(m):
    print(f'[{time.time() - T0:6.1f}s] {m}', flush=True)


F.use_build(BUILD)
PID = CZ.game_pid(BUILD)
log(f'game pid {PID}')


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
            log(f'zone {z}')
            return True
        time.sleep(1)
    log(f'TIMEOUT waiting for {name}; zone is {zone()}')
    return False


def shot(n):
    p = os.path.join(OUT, n + '.png')
    F.screenshot(p)
    log(f'shot {n}')
    return p


def wheel(n):
    F.down(['NUMPAD5']); time.sleep(0.7); shot(n); F.up(['NUMPAD5']); time.sleep(0.6)


def saves():
    return {p: os.path.getmtime(p) for p in glob.glob(os.path.join(SAVES, '**', '*'), recursive=True) if os.path.isfile(p)}


phase = sys.argv[1] if len(sys.argv) > 1 else 'all'
if phase in ('all', 'start'):
    time.sleep(4); shot('00_menu')
    F.key('RETURN'); time.sleep(2.5); F.key('RETURN')           # Begin Story, then the difficulty prompt's Normal
    if not wait_zone('nyc/alison/nyc1_1_1'):
        sys.exit(2)
    time.sleep(8); shot('01_nyc1_1_1')
    F.script(r'seatParty("wolverine","cyclops","","")\n\rloadMapKeepTeam("nyc/alison/nyc1_1_3")')
    if not wait_zone('nyc/alison/nyc1_1_3'):
        sys.exit(3)
    time.sleep(10); shot('02_nyc1_1_3')
    F.script(r'setAutoSpend(1,1)\n\rawardXPToPlayable(600)')   # a level for both, points auto-spent
    time.sleep(4); F.key('RETURN'); time.sleep(2); shot('03_leveled')
    F.key('RIGHT'); time.sleep(1.2); shot('04_cyclops_active')
    wheel('05_wheel_cyclops_before_load')
    F.key('LEFT'); time.sleep(1.2); wheel('06_wheel_wolverine_before_load')

if phase in ('all', 'save'):
    before = saves()
    used = None
    for cmd in ('savegame', 'savegame 0', 'savegame 1'):
        F.console(cmd); time.sleep(5)
        new = {p: m for p, m in saves().items() if p not in before or before[p] != m}
        if new:
            used = cmd; log(f'{cmd!r} wrote {sorted(os.path.basename(p) for p in new)}'); break
        log(f'{cmd!r}: no save file change')
    shot('07_after_save')
    if not used:
        log('no console save form worked - stop'); sys.exit(4)
    slot = used.split()[1] if ' ' in used else ''
    F.console(f'loadgame {slot}'.strip()); time.sleep(3); shot('08_loading'); time.sleep(14); shot('09_loaded')
    log(f'zone after load: {zone()}')
    wheel('10_wheel_hero1_after_load')
    F.key('RIGHT'); time.sleep(1.2); shot('11_switched'); wheel('12_wheel_hero2_after_load')
    F.key('LEFT'); time.sleep(1.2); wheel('13_wheel_hero1_again')
log('done')

if phase == 'redo':
    F.key('ESCAPE'); time.sleep(1.5)
    F.script(r'seatParty("cyclops","wolverine","","")\n\rloadMapKeepTeam("nyc/alison/nyc1_1_3")')
    wait_zone('nyc/alison/nyc1_1_3'); time.sleep(12); shot('20_cyclops_first')
    F.script(r'setAutoSpend(1,1)\n\rawardXPToPlayable(600)'); time.sleep(4); F.key('RETURN'); time.sleep(2)
    wheel('21_wheel_cyclops_before_save')
    before = saves()
    F.console('savegame'); time.sleep(2.5); shot('22_save_menu'); F.key('RETURN'); time.sleep(5); shot('23_after_enter')
    new = {p for p, m in saves().items() if p not in before or before[p] != m}
    if not new:
        F.key('RETURN'); time.sleep(5); new = {p for p, m in saves().items() if p not in before or before[p] != m}
    log(f'save files changed: {sorted(os.path.basename(p) for p in new)}')
    F.key('ESCAPE'); time.sleep(1.5)
    F.console('loadgame'); time.sleep(2.5); shot('24_load_menu'); F.key('RETURN'); time.sleep(3); shot('25_load_confirm')
    F.key('RETURN'); time.sleep(18); shot('26_loaded'); log(f'zone after load: {zone()}')
    wheel('27_wheel_cyclops_after_load')
    F.key('ESCAPE'); time.sleep(1)
    log('redo done')

if phase == 'load2':
    F.key('DOWN'); time.sleep(0.8); F.key('RETURN'); time.sleep(4); shot('30_loading')
    time.sleep(16); shot('31_loaded'); log(f'zone after load: {zone()}')
    wheel('32_wheel_hero1_after_load')
    log('load2 done')

if phase == 'fresh':
    # a fresh process: main menu -> Load Game -> the save made above (Owen's own flow)
    time.sleep(3); shot('40_menu')
    F.key('DOWN'); time.sleep(0.8); F.key('RETURN'); time.sleep(2.5); shot('41_load_menu')
    F.key('RETURN'); time.sleep(3); shot('42_after_select')
    if not wait_zone('nyc/alison/nyc1_1_3', 60):
        F.key('DOWN'); time.sleep(0.8); F.key('RETURN'); wait_zone('nyc/alison/nyc1_1_3', 60)
    time.sleep(14); shot('43_loaded'); log(f'zone: {zone()}')
    wheel('44_wheel_hero1_fresh_load')
    F.script('setActiveHero("wolverine")'); time.sleep(1.5); wheel('45_wheel_after_script_switch')
    log('fresh done')

if phase == 'loadnow':
    F.key('RETURN'); wait_zone('nyc/alison/nyc1_1_3', 90); time.sleep(14); shot('49_loaded_OLD_ORDER_control')
    log(f'zone: {zone()}'); wheel('50_wheel_OLD_ORDER_control'); log('loadnow done')

if phase == 'cont':
    F.key('RETURN'); wait_zone('nyc/alison/nyc1_1_3', 90); time.sleep(14); shot('49_loaded_OLD_ORDER_control')
    log(f'zone: {zone()}'); wheel('50_wheel_OLD_ORDER_control'); log('cont done')

if phase == 'bb':
    # blackbird_arbiter (its package lists cyclops/phoenix/storm/wolverine styles): a party of four OTHER heroes,
    # then a save + in-session load there; hero 1's wheel must stay filled (the engine's talent registry)
    time.sleep(4); shot('60_menu')
    F.key('RETURN'); time.sleep(2.5); F.key('RETURN')
    if not wait_zone('nyc/alison/nyc1_1_1'):
        sys.exit(2)
    time.sleep(8)
    F.script(r'seatParty("iceman","beast","rogue","jubilee")\n\rloadMapKeepTeam("xjet/blackbird_arbiter")')
    if not wait_zone('xjet/blackbird_arbiter'):
        sys.exit(3)
    time.sleep(12); shot('61_blackbird')
    F.script(r'setAutoSpend(1,1)\n\rawardXPToPlayable(600)'); time.sleep(4); F.key('RETURN'); time.sleep(2)
    wheel('62_wheel_iceman_after_level')
    before = saves()
    F.console('savegame'); time.sleep(2.5); F.key('RETURN'); time.sleep(5)
    new = {p for p, m in saves().items() if p not in before or before[p] != m}
    if not new:
        F.key('RETURN'); time.sleep(5); new = {p for p, m in saves().items() if p not in before or before[p] != m}
    log(f'save files changed: {sorted(os.path.basename(p) for p in new)}')
    F.key('ESCAPE'); time.sleep(1.5)
    F.console('loadgame'); time.sleep(2.5); F.key('RETURN'); time.sleep(3); shot('63_load_confirm')
    F.key('DOWN'); time.sleep(0.8); F.key('RETURN'); time.sleep(20); shot('64_loaded'); log(f'zone: {zone()}')
    wheel('65_wheel_iceman_after_load')
    log('bb done')

if phase == 'w12b':
    # the normal first play: Wolverine alone into nyc1_1_2b (its package now lists Cyclops's talents + style)
    time.sleep(4); F.key('RETURN'); time.sleep(2.5); F.key('RETURN')
    if not wait_zone('nyc/alison/nyc1_1_1'):
        sys.exit(2)
    time.sleep(8)
    F.script(r'loadMapKeepTeam("nyc/alison/nyc1_1_2b")')
    if not wait_zone('nyc/alison/nyc1_1_2b'):
        sys.exit(3)
    time.sleep(12); shot('70_nyc1_1_2b')
    wheel('71_wheel_wolverine_1_1_2b')
    F.script(r'setAutoSpend(1,1)\n\rawardXPToPlayable(600)'); time.sleep(4); F.key('RETURN'); time.sleep(2)
    wheel('72_wheel_wolverine_1_1_2b_leveled')
    log('w12b done')
