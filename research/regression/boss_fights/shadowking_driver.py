"""Shadow King (astral/savepx/final_astral) on XMen2.exe. sp_shadowking01 spawns at zone start (firstact 0.1,
monster_undying). XML1's design: sk1pain's 16 % thresholds -> sk3 (shield: only an Xtreme hurts him) + the
30 s shieldtimer -> sk4 (shield down); his death script spawnsk2 swaps him for shadowkingtwo (sk2), whose
sk2pain uses power_boost / power_xtreme combat nodes (data) and whose death runs shadowking_defeated."""
import sys, time
import boss_common as B

B.LOGFILE = B.OUT + '/shadowking.log'
Z = 'astral/savepx/final_astral'
steps = sys.argv[1:] or ['load', 'watch', 'stage', 'kill1', 'sk2', 'kill2']

if 'load' in steps:
    B.seat('wolverine', 'cyclops', 'storm', 'iceman')
    time.sleep(1)
    B.goto(Z, settle=10)
    B.invulnerable(True)
    B.log(f'zone {B.zone()}')
    B.frames('50_sk_loaded', 6, gap=2.0)

if 'watch' in steps:
    B.frames('51_sk_watch', 6, gap=2.0)

if 'stage' in steps:
    # sk1pain: next hit under 84 % -> sk3 (shield up in XML1) + shieldtimer; does damage keep landing here?
    B.fraction('shadowking', 0.80)
    time.sleep(0.5)
    B.teleport_party_to('shadowking')
    B.attack_burst('NUMPAD6', 4)
    B.frames('52_sk_stage2', 6, gap=1.5)
    B.teleport_party_to('shadowking')
    B.attack_burst('NUMPAD6', 8)
    B.frames('53_sk_stage2_more_hits', 4, gap=1.5)

if 'kill1' in steps:
    # monster_undying: can he reach 0? damage() then watch for spawnsk2 (EA_POWER7 anim, swap, sk2)
    B.fraction('shadowking', 0.03)
    time.sleep(0.5)
    B.teleport_party_to('shadowking')
    B.attack_burst('NUMPAD6', 8)
    B.frames('54_sk_low', 4, gap=1.5)
    B.script('damage("shadowking","shadowking",5000)')
    B.frames('55_sk_after_damage', 10, gap=1.5)

if 'sk2' in steps:
    B.teleport_party_to('shadowking2')
    B.attack_burst('NUMPAD6', 4)
    B.frames('56_sk2_fight', 6, gap=1.5)
    B.fraction('shadowking2', 0.45)
    B.attack_burst('NUMPAD6', 4)
    B.frames('57_sk2_stage', 6, gap=1.5)

if 'kill2' in steps:
    B.fraction('shadowking2', 0.03)
    time.sleep(0.5)
    B.attack_burst('NUMPAD6', 6)
    B.script('damage("shadowking2","shadowking2",5000)')
    for i in range(12):
        B.safe_shot(f'58_sk2_death_{i:02d}'); B.F.key('RETURN'); time.sleep(2)
    B.log(f'zone {B.zone()} responding {B.responding()}')
