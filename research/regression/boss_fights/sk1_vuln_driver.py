"""Shadow King phase 1 (final_astral): unreachable or immune? Fresh process, NO setInvulnerable on anyone.
Probes, each with bar readings before / after: (a) Cyclops's power at him from the floor (attackEntityWithType),
(b) Wolverine teleported onto him: smash key + a scripted heavy melee, (c) the same after
setInvulnerable("shadowking","FALSE"), (d) script damage() as the control that the bar reads damage."""
import sys, time
import boss_common as B

B.LOGFILE = B.OUT + '/sk1_vuln.log'
Z = 'astral/savepx/final_astral'
B.new_game()
B.seat('wolverine', 'cyclops', 'storm', 'iceman')
time.sleep(1)
B.F.script(f'loadMapKeepTeam("{Z}")')
if not B.wait_zone(Z, 120):
    sys.exit(3)
time.sleep(15)
B.log(f'zone {B.zone()} responding {B.responding()}')
B.frames('130_skv_loaded', 3, gap=1.5)

# (a) ranged power from the floor (Cyclops = _HERO2_), then Storm's
for i in range(3):
    B.script('attackEntityWithType("_HERO2_","shadowking","power_attack","FALSE")')
    time.sleep(2.5)
B.frames('131_skv_cyclops_floor', 3, gap=1.5)
for i in range(3):
    B.script('attackEntityWithType("_HERO3_","shadowking","power_attack","FALSE")')
    time.sleep(2.5)
B.frames('132_skv_storm_floor', 3, gap=1.5)

# (b) melee on the pillar
B.script('copyOriginAndAngles("_HERO1_","shadowking")')
time.sleep(1)
B.frames('133_skv_on_pillar', 2, gap=1.0)
B.attack_burst('NUMPAD6', 8, gap=0.4)
B.frames('134_skv_smash_pillar', 3, gap=1.5)
for i in range(3):
    B.script('attackEntityWithType("_HERO1_","shadowking","attackheavy1","FALSE")')
    time.sleep(2.0)
B.frames('135_skv_scripted_melee', 3, gap=1.5)
B.script('copyOriginAndAngles("_HERO2_","shadowking")')
time.sleep(1)
for i in range(3):
    B.script('attackEntityWithType("_HERO2_","shadowking","power_attack","FALSE")')
    time.sleep(2.5)
B.frames('136_skv_cyclops_pillar', 3, gap=1.5)

# (c) after clearing an invulnerable flag
B.script('setInvulnerable("shadowking","FALSE")')
time.sleep(0.5)
B.attack_burst('NUMPAD6', 8, gap=0.4)
for i in range(2):
    B.script('attackEntityWithType("_HERO2_","shadowking","power_attack","FALSE")')
    time.sleep(2.5)
B.frames('137_skv_after_vuln_false', 3, gap=1.5)

# (d) control: script damage
B.script('damage("shadowking","shadowking",500)')
time.sleep(1.5)
B.frames('138_skv_damage_control', 2, gap=1.0)
B.log(f'zone {B.zone()} responding {B.responding()}')
