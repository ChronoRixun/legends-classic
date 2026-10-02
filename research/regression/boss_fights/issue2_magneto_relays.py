"""Run after issue2_phases.py magneto; stage2 must have completed.

Exercises the later relay scripts with named damage. Helper deaths are represented
by relay activations; this does not claim a full fight against those helpers.
"""
import time
from issue2_measure import Evidence, command

frames = Evidence('astroid_m/visit1/asteroid2_1')
for stage in (3, 4, 5):
    command('setEnable("shieldup","TRUE")')
    command('act("shieldup","shieldup")')
    frames.shot(f'mag_stage{stage}_protected_before')
    command('damage("magneto","magneto",300)')
    frames.shot(f'mag_stage{stage}_protected_after')
    for _ in range(2):
        command(f'act("stage{stage}","stage{stage}")')
    time.sleep(1)
    frames.shot(f'mag_stage{stage}_released_before')
    command('damage("magneto","magneto",300)')
    frames.shot(f'mag_stage{stage}_released_after')
frames.save('magneto_all_phases')
