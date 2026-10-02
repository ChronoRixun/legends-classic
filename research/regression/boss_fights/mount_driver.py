"""Avalanche at the mountain (mount/mount/mount2) on XMen2.exe, from a fresh game. sp_avalancheact01
(aipattern avalanche: start = setstate avalanche, endbattle = setstate endbattle (an XMen2.exe state),
monster_undying, AI off at spawn; start_fight turns it on). XML1: avalanchepain's 10 % steps alternate
power_xtreme (+ rock drops via drop_relay) and power_boost combat nodes - data, not AI state - and the
fight ends by script (camcut -> endbattle + the avspot path, endscene removes him), not by his death."""
import sys, time
import boss_common as B

B.LOGFILE = B.OUT + '/mount.log'
Z = 'mount/mount/mount2'
steps = sys.argv[1:] or ['load', 'start', 'hit', 'stages', 'end']

if 'load' in steps:
    if not B.fresh_to(Z):
        sys.exit(4)
    B.frames('80_av_loaded', 4, gap=2.0)

if 'start' in steps:
    B.script('act("sp_avalancheact01","sp_avalancheact01")')
    time.sleep(2)
    B.F.script('mount/start_fight')
    time.sleep(2)
    B.teleport_party_to('avalanche')
    B.frames('81_av_fight', 8, gap=1.5)

if 'hit' in steps:
    B.teleport_party_to('avalanche')
    B.attack_burst('NUMPAD6', 6)
    B.frames('82_av_hit', 6, gap=1.5)

if 'stages' in steps:
    for frac, lab in ((0.75, '83_av_80'), (0.65, '84_av_70'), (0.55, '85_av_60'), (0.35, '86_av_40'), (0.05, '87_av_10')):
        B.fraction('avalanche', frac)
        time.sleep(0.5)
        B.teleport_party_to('avalanche')
        B.attack_burst('NUMPAD6', 4)
        B.frames(lab, 6, gap=1.5)

if 'end' in steps:
    # XML1 ends the fight by script: the camcut relay (endbattle) then endscene; monster_undying keeps him up
    B.script('damage("avalanche","avalanche",5000)')
    B.frames('88_av_after_damage', 6, gap=1.5)
    B.F.script('mount/camcut')
    time.sleep(3)
    B.frames('89_av_camcut', 6, gap=1.5)
    B.log(f'zone {B.zone()} responding {B.responding()}')
