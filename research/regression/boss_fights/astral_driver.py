"""Astral plane act 8 bosses on XMen2.exe, each from a fresh game (boss_common.fresh_to):
  pyro       astral/ast3/astral3_3: sp_pyro_astral01 (Vulcan, aipattern pyroastral: start/fireup/firedown =
             setstate pyroastral / setpyroastral true|false). XML1: pyrocam puts his shield up (shield_on combat
             node + setInvulnerable) and fire demons come in waves; pyropain's quarters -> next_stage (shield
             + fireup); four demon deaths -> firedown + shield_off + vulnerable for 10 s.
  avalanche  astral/ast3/astral3_4: avalanche_spawner (AvalancheAct4, aipattern avalanche_astral), started by
             avalanche_start (the_switch); avalanche_pain's 20 % steps: invulnerable + power_xtreme + do_cage
             (10 s) + pain_x / pain_o spawners.
  blob       astral/ast3/astral3_5: sp_blob_astral01 (BlobAct4, aipattern blobastral); blobpain's 16 % steps:
             armor_on + a pillar made breakable; the pillar's death -> armor_off + he grows (setScale).
  colosseum  astral/ast3/colosseum: the four dopples (dop_col/cyc/jean/wol), started by the conversation end
             (conv3_7_5end: setPatternSequence(<dopple>, "start")); dopple_death counts to 4 (-> relay_end),
             evilwolverine resurrects after 20 s."""
import sys, time
import boss_common as B

B.LOGFILE = B.OUT + '/astral.log'
which = sys.argv[1]
steps = sys.argv[2:] or ['all']


def want(s):
    return s in steps or 'all' in steps


if which == 'pyro':
    Z = 'astral/ast3/astral3_3'
    if want('load'):
        if not B.fresh_to(Z):
            sys.exit(4)
        B.frames('90_py_loaded', 4, gap=2.0)
    if want('start'):
        B.script('act("sp_pyro_astral01","sp_pyro_astral01")')
        time.sleep(2)
        B.F.script('astral/ast3/pyrocam')
        time.sleep(3)
        B.F.script('astral/ast3/pyro_start')
        time.sleep(2)
        B.frames('91_py_shielded', 8, gap=1.5)
    if want('hit'):
        B.teleport_party_to('pyro')
        B.attack_burst('NUMPAD6', 6)
        B.frames('92_py_hit_shielded', 4, gap=1.5)
    if want('demons'):
        # four demon deaths -> spawnfiredemons: firedown, shield_off, vulnerable
        for _ in range(4):
            B.F.script('astral/ast3/firedemondeath'); time.sleep(0.6)
        time.sleep(4)
        B.frames('93_py_vulnerable', 8, gap=1.5)
        B.teleport_party_to('pyro')
        B.attack_burst('NUMPAD6', 6)
        B.frames('94_py_hit_vulnerable', 4, gap=1.5)
    if want('kill'):
        B.fraction('pyro', 0.05)
        B.attack_burst('NUMPAD6', 4)
        B.script('damage("pyro","pyro",5000)')
        for i in range(6):
            B.safe_shot(f'95_py_kill_{i:02d}'); time.sleep(2)
        B.log(f'zone {B.zone()} responding {B.responding()}')

if which == 'avalanche':
    Z = 'astral/ast3/astral3_4'
    if want('load'):
        if not B.fresh_to(Z):
            sys.exit(4)
        B.frames('100_aa_loaded', 4, gap=2.0)
    if want('start'):
        B.F.script('astral/ast3/avalanche_start')
        time.sleep(3)
        B.F.script('astral/ast3/enable_avalanche')
        time.sleep(2)
        B.script('cameraReset()')
        B.teleport_party_to('avalanche')
        B.frames('101_aa_fight', 8, gap=1.5)
    if want('hit'):
        B.teleport_party_to('avalanche')
        B.attack_burst('NUMPAD6', 6)
        B.frames('102_aa_hit', 4, gap=1.5)
    if want('stage'):
        B.fraction('avalanche', 0.75)
        time.sleep(0.5)
        B.teleport_party_to('avalanche')
        B.attack_burst('NUMPAD6', 4)
        B.frames('103_aa_stage2', 12, gap=1.5)
    if want('kill'):
        B.fraction('avalanche', 0.05)
        B.attack_burst('NUMPAD6', 4)
        B.script('damage("avalanche","avalanche",5000)')
        for i in range(6):
            B.safe_shot(f'104_aa_kill_{i:02d}'); time.sleep(2)
        B.log(f'zone {B.zone()} responding {B.responding()}')

if which == 'blob':
    Z = 'astral/ast3/astral3_5'
    if want('load'):
        if not B.fresh_to(Z):
            sys.exit(4)
        B.frames('110_ab_loaded', 4, gap=2.0)
    if want('start'):
        B.script('act("sp_blob_astral01","sp_blob_astral01")')
        time.sleep(2)
        B.F.script('astral/ast3/enable_blob')
        time.sleep(3)
        B.teleport_party_to('blob')
        B.frames('111_ab_fight', 8, gap=1.5)
    if want('hit'):
        B.teleport_party_to('blob')
        B.attack_burst('NUMPAD6', 6)
        B.frames('112_ab_hit', 4, gap=1.5)
    if want('stage'):
        B.fraction('blob', 0.80)
        time.sleep(0.5)
        B.teleport_party_to('blob')
        B.attack_burst('NUMPAD6', 4)
        B.frames('113_ab_stage2_armor', 6, gap=1.5)
        B.attack_burst('NUMPAD6', 6)
        B.frames('114_ab_hit_armored', 4, gap=1.5)
        B.script('damage("blob_pillar01","blob_pillar01",5000)')
        time.sleep(2)
        B.frames('115_ab_pillar_dead', 6, gap=1.5)
    if want('kill'):
        B.fraction('blob', 0.05)
        B.attack_burst('NUMPAD6', 4)
        B.script('damage("blob","blob",5000)')
        for i in range(6):
            B.safe_shot(f'116_ab_kill_{i:02d}'); time.sleep(2)
        B.log(f'zone {B.zone()} responding {B.responding()}')

if which == 'colosseum':
    Z = 'astral/ast3/colosseum'
    if want('load'):
        if not B.fresh_to(Z):
            sys.exit(4)
        for i in range(10):
            B.safe_shot(f'120_col_intro_{i:02d}'); B.F.key('RETURN'); time.sleep(2)
    if want('start'):
        B.F.script('astral/ast3/colosseum_introcam3')
        time.sleep(3)
        B.F.script('astral/ast3/conv3_7_5end')
        time.sleep(5)
        B.frames('121_col_fight', 10, gap=1.5)
    if want('hit'):
        for n in ('evilcyc', 'evilwolverine', 'eviljean', 'evilcolossus'):
            B.teleport_party_to(n)
            B.attack_burst('NUMPAD6', 4)
            B.frames(f'122_col_hit_{n}', 3, gap=1.0)
    if want('kill'):
        for n in ('evilcyc', 'eviljean', 'evilcolossus', 'evilwolverine'):
            B.script(f'damage("{n}","{n}",9000)')
            time.sleep(2)
        for i in range(8):
            B.safe_shot(f'123_col_kill_{i:02d}'); B.F.key('RETURN'); time.sleep(2)
        B.log(f'zone {B.zone()} responding {B.responding()}')
