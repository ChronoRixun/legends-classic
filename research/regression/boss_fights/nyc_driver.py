"""NYC act 1 bosses on XMen2.exe, each from a fresh new game (boss_common.fresh_to):
  mystique  nyc/alison/nyc1_1_2b: mystique_spawner02 (aipattern mystique: myst1..3, monster_undying,
            monster_aiforceranged). XML1: myst1 at spawn (mystiquespawn), mystique_pain's quarters: stage 2 ->
            she runs away (mystiqueaway path) and round1grunts; 3 grunts dead -> myst3 + back; stage 3 -> myst3;
            stage 4 -> round2grunts + she morphs into a grunt (mystiquegrunt); the objective completes on the
            disguised grunt's death (grunt2death).
  blob      nyc/alison/nyc1_1_3: spawner blob (aipattern blobnyc, instantspawn, radius confinement 708 around
            wp_blob_center, AI off until the conversation); pain script = a popup relay; deathscript = the
            1_1_5_2 conversation (defeat_blob objective)."""
import sys, time
import boss_common as B

B.LOGFILE = B.OUT + '/nyc.log'
which = sys.argv[1]
steps = sys.argv[2:] or ['all']

if which == 'mystique':
    Z = 'nyc/alison/nyc1_1_2b'
    if 'load' in steps or 'all' in steps:
        if not B.fresh_to(Z):
            sys.exit(4)
        B.frames('60_my_loaded', 4, gap=2.0)
    if 'start' in steps or 'all' in steps:
        # the fight starts from the park-gate trigger (mystique_fight_start): run it directly
        B.F.script('nyc/alison/mystique_fight_start')
        time.sleep(12)
        B.frames('61_my_start', 8, gap=1.5)
    if 'hit' in steps or 'all' in steps:
        B.teleport_party_to('mystique')
        time.sleep(0.5)
        B.attack_burst('NUMPAD6', 6)
        B.frames('62_my_hit', 6, gap=1.5)
    if 'stage2' in steps or 'all' in steps:
        B.fraction('mystique', 0.70)
        time.sleep(0.5)
        B.teleport_party_to('mystique')
        B.attack_burst('NUMPAD6', 4)
        B.frames('63_my_stage2', 10, gap=2.0)
    if 'grunts' in steps or 'all' in steps:
        # the three round-1 grunts' deaths (grunt1death x3) -> myst3 + mystiqueback path
        for _ in range(3):
            B.F.script('nyc/alison/grunt1death'); time.sleep(0.5)
        time.sleep(3)
        B.frames('64_my_after_grunts', 8, gap=2.0)
    if 'stage3' in steps or 'all' in steps:
        B.fraction('mystique', 0.45)
        time.sleep(0.5)
        B.teleport_party_to('mystique')
        B.attack_burst('NUMPAD6', 4)
        B.frames('65_my_stage3', 6, gap=2.0)
    if 'stage4' in steps or 'all' in steps:
        B.fraction('mystique', 0.20)
        time.sleep(0.5)
        B.teleport_party_to('mystique')
        B.attack_burst('NUMPAD6', 4)
        B.frames('66_my_stage4', 10, gap=2.0)
    if 'kill' in steps or 'all' in steps:
        # stage 4: she is a disguised grunt (mystiquegrunt, deathscript grunt2death -> objective)
        B.script('damage("mystiquegrunt","mystiquegrunt",5000)')
        time.sleep(2)
        B.script('damage("mystique","mystique",5000)')
        for i in range(8):
            B.safe_shot(f'67_my_kill_{i:02d}'); B.F.key('RETURN'); time.sleep(2)
        B.log(f'zone {B.zone()} responding {B.responding()}')

if which == 'blob':
    Z = 'nyc/alison/nyc1_1_3'
    if 'load' in steps or 'all' in steps:
        if not B.fresh_to(Z):
            sys.exit(4)
        B.frames('70_blob_loaded', 4, gap=2.0)
    if 'start' in steps or 'all' in steps:
        # blobspawn turned his AI off for the intro; the conversation end turns it on - do it directly
        B.script('setAIActive("blob","TRUE")', 'setReactToEnemies("blob","TRUE")', 'setDefaultTarget("blob")')
        B.teleport_party_to('blob')
        time.sleep(2)
        B.frames('71_blob_fight', 10, gap=1.5)
    if 'hit' in steps or 'all' in steps:
        B.teleport_party_to('blob')
        B.attack_burst('NUMPAD6', 8)
        B.frames('72_blob_hit', 6, gap=1.5)
        B.fraction('blob', 0.30)
        B.attack_burst('NUMPAD6', 4)
        B.frames('73_blob_low', 6, gap=1.5)
    if 'kill' in steps or 'all' in steps:
        B.fraction('blob', 0.02)
        B.attack_burst('NUMPAD6', 6)
        B.script('damage("blob","blob",5000)')
        for i in range(8):
            B.safe_shot(f'74_blob_kill_{i:02d}'); B.F.key('RETURN'); time.sleep(2)
        B.log(f'zone {B.zone()} responding {B.responding()}')
