"""Asteroid M Magneto fight (astroid_m/visit1/asteroid2_1) on XMen2.exe: spawn through trigger_touch06, click
through the conversation, then force magneto_pain's 25 % stages with setHealth + hits and watch what the
boss does after each setPatternSequence("magneto", mag2..mag5 / magshield) that XMen2.exe cannot apply.
Frames + bar percentages in the scratchpad; the game must already be in a loaded game (boss_common.new_game)."""
import sys, time
import boss_common as B

B.LOGFILE = B.OUT + '/magneto.log'
Z = 'astroid_m/visit1/asteroid2_1'
steps = sys.argv[1:] or ['load', 'spawn', 'stage2', 'acolytes', 'stage3', 'sabre', 'stage4', 'mystique', 'kill']

if 'load' in steps:
    B.seat('wolverine', 'cyclops', 'storm', 'iceman')
    time.sleep(1)
    B.goto(Z, settle=8)
    B.invulnerable(True)
    B.log(f'zone {B.zone()}')
    B.shot('20_mag_loaded')

if 'spawn' in steps:
    # the touch trigger's acttargets spawn Magneto, the elite acolytes and the conversation Mystique
    B.script('act("trigger_touch06","trigger_touch06")')
    time.sleep(4)
    for i in range(8):
        p = B.shot(f'21_mag_conv_{i:02d}')
        B.F.key('RETURN'); time.sleep(2.0)
    time.sleep(3)
    B.frames('22_mag_fight', 6, gap=1.5)

if 'stage2' in steps:
    # magneto_pain: next hit below 75 % -> stage 2, health capped at 75 %, act shieldup (magshield), stage2 1/4
    B.teleport_party_to('magneto')
    B.fraction('magneto', 0.70)
    time.sleep(0.5)
    B.attack_burst('NUMPAD6', 4)
    B.frames('23_mag_stage2', 6, gap=1.5)

if 'acolytes' in steps:
    # the three elite acolytes' deaths act stage2 (4/4 with the pain act) -> stage2.py: mag2 + Sabretooth
    for n in ('ss_acolyteenergyb14', 'ss_acolyteleaderb03', 'ss_acolyteleaderb07'):
        B.script(f'killEntity("{n}")')
        time.sleep(0.5)
    time.sleep(2)
    B.frames('24_mag_after_acolytes', 8, gap=1.5)

if 'stage3' in steps:
    B.teleport_party_to('magneto')
    B.fraction('magneto', 0.45)
    time.sleep(0.5)
    B.attack_burst('NUMPAD6', 4)
    B.frames('25_mag_stage3', 6, gap=1.5)

if 'sabre' in steps:
    B.script('killEntity("sabretooth")')
    time.sleep(3)
    B.frames('26_mag_after_sabre', 8, gap=1.5)

if 'stage4' in steps:
    B.teleport_party_to('magneto')
    B.fraction('magneto', 0.20)
    time.sleep(0.5)
    B.attack_burst('NUMPAD6', 4)
    B.frames('27_mag_stage4', 6, gap=1.5)

if 'mystique' in steps:
    # mystiquepain at 50 % acts stage4 (2/2) -> mag4 + Sabretooth back; her death + Sabretooth's -> stage5
    B.fraction('mystique', 0.40)
    B.teleport_party_to('mystique')
    B.attack_burst('NUMPAD6', 4)
    time.sleep(2)
    B.frames('28_mag_mystique_half', 4, gap=1.5)
    B.script('killEntity("mystique")')
    time.sleep(2)
    B.script('killEntity("sabretooth")')
    time.sleep(3)
    B.frames('29_mag_stage5', 8, gap=1.5)

if 'kill' in steps:
    B.teleport_party_to('magneto')
    B.fraction('magneto', 0.02)
    time.sleep(0.5)
    B.attack_burst('NUMPAD6', 8)
    for i in range(10):
        B.shot(f'30_mag_death_{i:02d}'); B.F.key('RETURN'); time.sleep(2)
    B.log(f'zone {B.zone()}')
