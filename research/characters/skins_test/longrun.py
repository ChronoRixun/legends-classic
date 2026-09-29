"""A long session before the Magneto room (the late test had walked ~20 zones first): Begin Story, loadMapKeepTeam
through a list of zones, then XML1's own path into asteroid2_1 (begin_asteroid_rock, begin_asteroid_int, XP, the
zone link) and the meeting trigger; screenshots of the conversation camera and the fight.

usage: longrun.py <tag>
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drive as D                               # noqa: E402
from magneto import sheet, wait_pipe            # noqa: E402

ZONES = ['mansion/man8/subbasement8', 'mansion/man8/hangar8', 'mansion/man8/mansion8_1', 'mansion/man8/mansion8_2',
         'astral/savepx/astral2_1', 'astral/savepx/astral2_2', 'astral/savepx/astral2_3',
         'astroid_m/visit1/asteroid1_1', 'astroid_m/visit1/asteroid1_2', 'astroid_m/visit1/asteroid2_2',
         'astroid_m/visit1/asteroid2_3', 'mastermold/mastermold1', 'mastermold/mastermold2',
         'nyc/alison/nyc1_1_2', 'nyc/alison/nyc1_1_4', 'arbiter/a_int/arb2_1', 'arbiter/a_int/arb2_2']


def fps():
    s = D.ask('status')
    try:
        return float(s.split('fps ')[1].split(';')[0])
    except (IndexError, ValueError):
        return 0.0


def settle(limit=240):
    """after a zone change: wait for the load (fps drops) and then for frames again."""
    time.sleep(8)
    t0 = time.time()
    while time.time() - t0 < limit:
        if fps() >= 5:
            time.sleep(4)
            if fps() >= 5:
                return round(time.time() - t0, 1)
        time.sleep(2)
    return None


def queue(fn, arg, tries=20):
    for _ in range(tries):
        try:
            return fn(arg)
        except Exception as ex:                  # console queue full while loading
            print('   retry', ex)
            time.sleep(3)
    raise SystemExit('could not queue ' + arg)


def invulnerable():
    queue(D.fixinput.script, r'setInvulnerable("_HERO1_","TRUE")\n\rsetInvulnerable("_HERO2_","TRUE")')
    time.sleep(1)
    queue(D.fixinput.script, r'setInvulnerable("_HERO3_","TRUE")\n\rsetInvulnerable("_HERO4_","TRUE")')
    time.sleep(1)


def main(argv):
    tag = argv[0]
    if D.pid() is None:
        import subprocess
        subprocess.run(['cmd', '/c', 'start', '', 'XMen2.exe'], cwd=D.BUILD)
    D._PID = None
    print(wait_pipe())
    t0 = time.time()
    while time.time() - t0 < 300:                 # the main menu: Begin Story once the game reads its keyboard
        time.sleep(5)
        if fps() < 20:
            continue
        try:
            D.ask('tap RETURN 120')
        except Exception as ex:
            print('   menu not ready', ex)
            continue
        time.sleep(5)
        if (D.zone() or 'menu').startswith('nyc'):
            break
    print('nyc', settle(), D.zone(), flush=True)
    for z in ([] if '--short' in argv else ZONES):
        queue(D.fixinput.script, f'loadMapKeepTeam("{z}")')
        w = settle()
        print(z, '->', D.zone(), w, D.ask('status').split('; ')[-4:], flush=True)
        if D.conv().get('active'):
            D.talk(20)
    if '--menu' in argv:                           # the late test: a game over -> Main Menu -> Begin Story again
        print('before menu', D.ask('status'), flush=True)
        queue(D.fixinput.script, 'mainMenuExit()')
        time.sleep(15)
        for _ in range(60):
            if (D.zone() or '').startswith('menu'):
                break
            time.sleep(3)
        print('menu', D.zone(), settle(), D.ask('status'), flush=True)
        t0 = time.time()
        while time.time() - t0 < 300:
            time.sleep(5)
            try:
                D.ask('tap RETURN 120')
            except Exception as ex:
                print('   menu not ready', ex)
                continue
            time.sleep(6)
            if (D.zone() or 'menu').startswith('nyc'):
                break
        print('nyc again', settle(), D.zone(), D.ask('status'), flush=True)
    queue(D.fixinput.console, 'runscript x1/missions/begin_asteroid_rock')
    if '--movie' in argv:                          # r302 plays first (the late test skipped it with Enter)
        for i in range(4):
            time.sleep(5)
            D.shot(f'{tag}_movie_{i}')
        D.ask('tap RETURN 120')
    print('rock', settle(), D.zone(), flush=True)
    for _ in range(60):
        if (D.zone() or '').endswith('asteroid1_1'):
            break
        time.sleep(3)
    print('rock zone', D.zone(), settle(), flush=True)
    D.talk(60)
    time.sleep(2)
    D.talk(30)
    queue(D.fixinput.console, 'runscript x1/missions/begin_asteroid_int')
    print('int', settle(), D.zone(), flush=True)
    D.talk(60)
    queue(D.fixinput.script, 'awardXPToPlayable(8411600)')
    time.sleep(3)
    D.ask('tap RETURN 120')                       # the level-up popup
    time.sleep(2)
    invulnerable()
    queue(D.fixinput.script, 'copyOriginAndAngles("_ACTIVE_HERO_","zone_link02")')
    time.sleep(2)
    for _ in range(5):
        D.ask('tap E 150')
        time.sleep(3)
        if (D.zone() or '').endswith('asteroid2_1'):
            break
    print('a21', settle(), D.zone(), D.ask('status'), flush=True)
    invulnerable()
    queue(D.fixinput.script, 'act("trigger_touch06","_ACTIVE_HERO_")')
    names = []
    for i in range(6):
        time.sleep(1.5)
        names.append(D.shot(f'{tag}_meet_{i}'))
    print(sheet(names, os.path.join(D.SHOTS, f'{tag}_meet_sheet.png')))
    D.talk(120)
    time.sleep(2)
    names = []
    for i in range(10):
        time.sleep(1.5)
        names.append(D.shot(f'{tag}_fight_{i}'))
    print(sheet(names, os.path.join(D.SHOTS, f'{tag}_fight_sheet.png')))
    print(D.ask('status'))


if __name__ == '__main__':
    main(sys.argv[1:])
