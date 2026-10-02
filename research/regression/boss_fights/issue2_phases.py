"""Issue 2 before/after encounter probes. See ISSUE2.md for setup and limitations."""
import ctypes
import os
import sys
import time
from pathlib import Path

import boss_common as B
from current_zone import proc_path
from issue2_measure import Evidence, command

assert Path(proc_path(B.PID)).parent == Path(B.BUILD)
# A minimized D3D window yields stale captures. Restore without activation.
hwnd = B.game_hwnd()
if hwnd:
    ctypes.windll.user32.ShowWindow(hwnd, 4)
case = sys.argv[1]
expected_zone = {
    'magneto': 'astroid_m/visit1/asteroid2_1',
    'mastermold': 'mastermold/mastermold2',
    'shadowking': 'astral/savepx/final_astral',
}[case]
B.LOGFILE = os.path.join(B.OUT, case + '.log')
frames = Evidence(expected_zone)


def hit(boss, label, n=8):
    command(f'setDefaultTarget("{boss}")')
    B.teleport_party_to(boss)
    time.sleep(1.3)
    command(f'x=getPosX("{boss}")', 'x=iadd(x,150)', 'setPosX("_HERO1_",x)')
    command(f'faceEntity("_HERO1_","{boss}")')
    frames.shot(label + '_before')
    B.attack_burst('NUMPAD6', n, gap=.45)
    time.sleep(1)
    frames.shot(label + '_after')


if B.zone().startswith('menu'):
    B.new_game()
B.seat('wolverine', 'cyclops', 'storm', 'iceman')
time.sleep(1)
B.goto(expected_zone, settle=15)
# A delayed New Game load can displace the initial jump; re-enter after it settles.
if B.zone() != expected_zone:
    B.goto(expected_zone, settle=15)
assert B.zone() == expected_zone, B.zone()
B.shot('loaded_' + case)
B.invulnerable(True)
time.sleep(1)
for hero in (2, 3, 4):
    command(f'setAIActive("_HERO{hero}_","FALSE")')

if case == 'magneto':
    command('act("trigger_touch06","trigger_touch06")')
    time.sleep(2)
    for _ in range(9):
        B.F.key('RETURN')
        time.sleep(1.5)
    hit('magneto', 'mag_initial')
    command('act("shieldup","shieldup")')
    time.sleep(2)
    hit('magneto', 'mag_shield')
    # Four inputs: the pain threshold plus three acolyte deaths.
    for _ in range(4):
        command('act("stage2","stage2")')
    time.sleep(3)
    hit('magneto', 'mag_stage2')
elif case == 'mastermold':
    hit('mastermold', 'mm_shield', n=24)
    # issue2_core_control.py stages the existing core check in this process.
else:
    hit('shadowking', 'sk_initial')
    B.fraction('shadowking', .80)
    time.sleep(1)
    hit('shadowking', 'sk_threshold')
    hit('shadowking', 'sk_shield')
    time.sleep(32)
    hit('shadowking', 'sk_timer_expired')
frames.save(case)
