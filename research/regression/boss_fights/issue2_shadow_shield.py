"""Run in a fresh first-form encounter after issue2_phases.py shadowking.

Clear the separate AI power_boost buff to isolate the scripted shield timer.
Phase/health are staged; real hero hits invoke the pain script and finish phase one.
"""
import time
import boss_common as B
from issue2_measure import Evidence, command

frames = Evidence('astral/savepx/final_astral')
command('setAIActive("shadowking","FALSE")', 'setCombatNode("shadowking","idle")')
time.sleep(33)
command('setInvulnerable("shadowking","FALSE")')
for bit in range(1, 6):
    command(f'setGameFlag("x1v02",{bit},{int(bit == 1)})')
command('setGameFlag("x1v01",27,0)')
B.fraction('shadowking', .65)
command('setDefaultTarget("shadowking")')
command('copyOriginAndAngles("_HERO1_","shadowking")')
command('x=getPosX("shadowking")', 'x=iadd(x,-80)', 'setPosX("_HERO1_",x)')
command('faceEntity("_HERO1_","shadowking")')
time.sleep(1)
B.attack_burst(n=3)
time.sleep(1)
frames.shot('sk_protected_confirmed_before')
B.attack_burst(n=10)
time.sleep(1)
frames.shot('sk_protected_confirmed_after')
time.sleep(32)
frames.shot('sk_unprotected_confirmed_before')
B.attack_burst(n=10)
time.sleep(1)
frames.shot('sk_unprotected_confirmed_after')
# Stage the last damage window; the phase-ending blow must still be a hero attack.
command('setInvulnerable("shadowking","FALSE")')
for bit in range(1, 6):
    command(f'setGameFlag("x1v02",{bit},{(6 >> (bit - 1)) & 1})')
command('setGameFlag("x1v01",27,0)', 'setHealth("shadowking",1)')
command('copyOriginAndAngles("_HERO1_","shadowking")')
command('x=getPosX("shadowking")', 'x=iadd(x,-80)', 'setPosX("_HERO1_",x)')
command('faceEntity("_HERO1_","shadowking")')
B.attack_burst(n=12)
time.sleep(4)
frames.shot('sk_phase1_ordinary_hit_finish')
frames.save('shadowking_confirmed')
