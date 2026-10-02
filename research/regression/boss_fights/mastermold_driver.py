"""Master Mold (mastermold/mastermold2) on XMen2.exe. The boss spawns at zone start (firstact 0.1, mmspawn).
XML1's design: mold1 = shielded (shockshield_on: def_damage 0 + touch damage) until the three warp-core
switches are used (core_on1..3 -> checkcore -> shockshield_off); mmpain's thirds -> mold2 (+ spawnsentinels
cinematic) and mold3; spawnsentinels ends with moldblowcore. Here: watch what he does unshielded, whether
the shield ever comes up, force the thirds with setHealth + hits, then kill him by damage -> stage3death (R501)."""
import sys, time
import boss_common as B

B.LOGFILE = B.OUT + '/mastermold.log'
Z = 'mastermold/mastermold2'
steps = sys.argv[1:] or ['load', 'watch', 'hit', 'stage2', 'stage3', 'kill']

if 'load' in steps:
    B.seat('wolverine', 'cyclops', 'storm', 'iceman')
    time.sleep(1)
    B.goto(Z, settle=10)
    B.invulnerable(True)
    B.log(f'zone {B.zone()}')
    B.frames('40_mm_loaded', 6, gap=2.0)

if 'watch' in steps:
    # is he shielded (mold_shield_loop effect) / attacking / idle before anyone touches the cores?
    B.frames('41_mm_watch', 8, gap=2.0)

if 'hit' in steps:
    # does damage land without the warp cores? (XML1: no, the shockshield's def_damage 0)
    B.teleport_party_to('mastermold')
    time.sleep(0.5)
    B.attack_burst('NUMPAD6', 6)
    B.frames('42_mm_hit', 4, gap=1.5)

if 'stage2' in steps:
    # mmpain: next hit under 66.7 % -> stage 2 (cap), mold2 + spawnsentinels (camera tour, ends with moldblowcore)
    B.fraction('mastermold', 0.60)
    time.sleep(0.5)
    B.teleport_party_to('mastermold')
    B.attack_burst('NUMPAD6', 4)
    B.frames('43_mm_stage2', 16, gap=2.0)

if 'stage3' in steps:
    B.fraction('mastermold', 0.30)
    time.sleep(0.5)
    B.teleport_party_to('mastermold')
    B.attack_burst('NUMPAD6', 4)
    B.frames('44_mm_stage3', 8, gap=2.0)

if 'kill' in steps:
    B.fraction('mastermold', 0.03)
    time.sleep(0.5)
    B.teleport_party_to('mastermold')
    B.attack_burst('NUMPAD6', 6)
    time.sleep(1)
    B.script('damage("mastermold","mastermold",5000)')
    for i in range(12):
        B.safe_shot(f'45_mm_death_{i:02d}'); time.sleep(2)
    B.log(f'zone {B.zone()} responding {B.responding()}')
