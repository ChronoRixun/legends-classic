"""Launch build/_skins (pipe skins), Begin Story, load Asteroid M's Magneto room (astroid_m/visit1/asteroid2_1),
trigger the meeting (trigger_touch06 spawns Magneto, Mystique, AcolyteEnergy_B x1, AcolyteLeader_B x2) and take
screenshots of the conversation camera and the fight.

usage: magneto.py <tag> [--party]     (--party: begin_asteroid_rock first for XML1's 4-hero party)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drive as D  # noqa: E402

from PIL import Image  # noqa: E402


def wait_pipe(limit=90):
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            return D.ask('status')
        except BaseException:        # fixinput exits when the pipe is not up yet
            D.fixinput._PIPE = None if hasattr(D.fixinput, '_PIPE') else None
            time.sleep(2)
    raise SystemExit('pipe never came up')


def wait_fps(limit=240, need=20.0):
    t0 = time.time()
    while time.time() - t0 < limit:
        s = D.ask('status')
        try:
            fps = float(s.split('fps ')[1].split(';')[0])
        except (IndexError, ValueError):
            fps = 0
        if fps >= need:
            return round(time.time() - t0, 1)
        time.sleep(2)
    return None


def invulnerable():
    D.fixinput.script(r'setInvulnerable("_HERO1_","TRUE")\n\rsetInvulnerable("_HERO2_","TRUE")')
    time.sleep(1)
    D.fixinput.script(r'setInvulnerable("_HERO3_","TRUE")\n\rsetInvulnerable("_HERO4_","TRUE")')
    time.sleep(1)


def sheet(names, out, scale=0.5, cols=2):
    ims = [Image.open(n) for n in names]
    w, h = int(ims[0].width * scale), int(ims[0].height * scale)
    rows = (len(ims) + cols - 1) // cols
    W = Image.new('RGB', (w * cols, h * rows))
    for k, im in enumerate(ims):
        W.paste(im.resize((w, h)), ((k % cols) * w, (k // cols) * h))
    W.save(out)
    return out


def main(argv):
    tag = argv[0]
    party = '--party' in argv
    if D.pid() is None:
        subprocess = __import__('subprocess')
        subprocess.run(['cmd', '/c', 'start', '', 'XMen2.exe'], cwd=D.BUILD)
        print('launched')
    D._PID = None
    print(wait_pipe())
    print('menu after', wait_fps(120, 30))
    time.sleep(2)
    D.shot(f'{tag}_00_menu')
    D.ask('tap RETURN 120')
    time.sleep(5)
    print('nyc after', wait_fps(240, 20), D.zone())
    time.sleep(3)
    if party:
        D.fixinput.console('runscript x1/missions/begin_asteroid_rock')
        print('asteroid1_1', D.wait_zone('astroid_m/visit1/asteroid1_1', 240))
        print('loaded after', wait_fps(240, 20))
        time.sleep(3)
        D.talk(60)
        time.sleep(2)
        D.talk(30)
    if '--late' in argv:            # the late test's own path: asteroid_int -> asteroid1_3, XP, zone link (E)
        D.fixinput.console('runscript x1/missions/begin_asteroid_int')
        print('asteroid1_3', D.wait_zone('astroid_m/visit1/asteroid1_3', 240))
        print('loaded after', wait_fps(240, 15))
        time.sleep(3)
        D.talk(60)
        D.fixinput.script('awardXPToPlayable(8411600)')
        time.sleep(2)
        invulnerable()
        D.shot(f'{tag}_01a_asteroid1_3')
        D.fixinput.script('copyOriginAndAngles("_ACTIVE_HERO_","zone_link02")')
        time.sleep(2)
        for _ in range(4):
            D.ask('tap E 150')
            time.sleep(2)
            if (D.zone() or '').endswith('asteroid2_1'):
                break
    else:
        D.fixinput.script('loadMapKeepTeam("astroid_m/visit1/asteroid2_1")')
    print('asteroid2_1', D.wait_zone('astroid_m/visit1/asteroid2_1', 240))
    time.sleep(5)
    print('loaded after', wait_fps(300, 20))
    time.sleep(3)
    invulnerable()
    D.shot(f'{tag}_01_room')
    D.fixinput.script('act("trigger_touch06","_ACTIVE_HERO_")')
    names = []
    for i in range(6):
        time.sleep(1.5)
        names.append(D.shot(f'{tag}_02_meet_{i}'))
    print(sheet(names, os.path.join(D.SHOTS, f'{tag}_02_meet_sheet.png')))
    D.talk(120)
    time.sleep(2)
    names = []
    for i in range(10):
        time.sleep(1.5)
        names.append(D.shot(f'{tag}_03_fight_{i}'))
    print(sheet(names, os.path.join(D.SHOTS, f'{tag}_03_fight_sheet.png')))
    print(D.ask('status'))


if __name__ == '__main__':
    main(sys.argv[1:])
