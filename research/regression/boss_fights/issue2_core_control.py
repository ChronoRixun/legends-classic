"""Run after issue2_phases.py mastermold, in the same isolated process.

Stages the existing core-check preconditions; does not claim a natural core puzzle run.
Compare the boss title in every image. The ordinary-hit probe may target a spider mine.
"""
import time
import boss_common as B
from issue2_measure import Evidence, command

frames = Evidence('mastermold/mastermold2')
command('setDefaultTarget("mastermold")')
frames.shot('mm_spawn_before_damage')
command('damage("mastermold","mastermold",1000)')
frames.shot('mm_spawn_after_damage')
# Isolate the existing shield node before exercising the unmodified core-check relay.
command('setCombatNode("mastermold","shockshield_on")')
time.sleep(4)
frames.shot('mm_control_on_before')
command('damage("mastermold","mastermold",5000)')
frames.shot('mm_control_on_after_damage')
command('setZoneVar("coresgone",3)', 'setGameFlag("x1v05",8,1)', 'setGameFlag("x1v05",9,1)')
command('setGameFlag("x1v05",10,0)')
command('act("checkcore","checkcore")')
time.sleep(10)
frames.shot('mm_corecheck_before_damage')
command('damage("mastermold","mastermold",5000)')
frames.shot('mm_corecheck_after_damage')
frames.save('mastermold_core_control')
