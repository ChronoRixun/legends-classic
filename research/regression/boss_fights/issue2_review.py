"""Review probes for PR #23; fresh process per case, see ISSUE2.md.

Master Mold never stages health, phases, core counters or checkcore. Named damage
only crosses his normal pain thresholds; the switches use their normal act path.
Shadow King's placement observation never teleports the boss or party.
"""
import sys
import time
import boss_common as B
from issue2_measure import Evidence, command

case = sys.argv[1]
zone = {'shadowking': 'astral/savepx/final_astral',
        'mastermold': 'mastermold/mastermold2',
        'magneto': 'astroid_m/visit1/asteroid2_1'}[case]
if B.zone().startswith('menu'):
    B.new_game()
B.seat('wolverine', 'cyclops', 'storm', 'iceman')
time.sleep(1)
B.goto(zone, settle=0 if case == 'shadowking' else 12)
if case == 'shadowking':
    for frame in range(8):
        B.shot(f'sk_entry_{frame}')
        time.sleep(1)
if B.zone() != zone:
    B.goto(zone, settle=12)
assert B.zone() == zone
B.invulnerable(True)
time.sleep(1)
frames = Evidence(zone)

if case == 'shadowking':
    command('setDefaultTarget("shadowking")')
    # Observe the party at the zone start and the boss approaching under normal AI.
    for n in range(6):
        frames.shot(f'sk_approach_{n}')
        B.attack_burst(n=6, gap=.4)
        time.sleep(1)
elif case == 'mastermold':
    command('setDefaultTarget("mastermold")')
    command('setHealthMax("_ACTIVE_HERO_",100000)', 'restoreHealth("_ACTIVE_HERO_",100000)')
    for hero in (2, 3, 4):
        command(f'setAIActive("_HERO{hero}_","FALSE")')
    frames.shot('mm_unstaged_spawn')
    B.teleport_party_to('mastermold')
    B.attack_burst(n=24, gap=.4)
    frames.shot('mm_hero_attacks')
    # No health assignment, stage assignment, core counters or checkcore activation.
    for n in range(1, 11):
        command('damage("mastermold","mastermold",1000)')
        time.sleep(3)
        frames.shot(f'mm_damage_{n}')
        if n == 5:
            # Let the sentinel drop-in scene complete before the next threshold.
            time.sleep(20)
            frames.shot('mm_after_sentinel_scene')
    for core in (1, 2, 3):
        command(f'act("warpcore_switch0{core}","warpcore_switch0{core}")')
    frames.shot('mm_switches_on')
    time.sleep(92)
    frames.shot('mm_switch_window_expired')
    command('damage("mastermold","mastermold",1000)')
    time.sleep(2)
    frames.shot('mm_after_window_damage')
else:
    command('act("trigger_touch06","trigger_touch06")')
    time.sleep(2)
    for _ in range(9):
        B.F.key('RETURN')
        time.sleep(1.5)
    # Three helpers dead first; pain is the fourth input. No shield1remover act.
    for _ in range(3):
        command('act("stage2","stage2")')
    B.fraction('magneto', .76)
    B.teleport_party_to('magneto')
    command('x=getPosX("magneto")', 'x=iadd(x,-80)', 'setPosX("_HERO1_",x)')
    command('faceEntity("_HERO1_","magneto")')
    command('setDefaultTarget("magneto")')
    frames.shot('mag_helpers_first_before')
    for n in range(4):
        B.attack_burst(n=12, gap=.4)
        time.sleep(1)
        frames.shot(f'mag_helpers_first_hits_{n}')
frames.save('review_' + case)
