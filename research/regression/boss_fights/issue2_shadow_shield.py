import os,sys,time,json
from pathlib import Path
import boss_common as B
from PIL import Image
r=[]
def cmd(*x):B.script(*x);time.sleep(.6)
def shot(n):
 p=B.shot(n); im=Image.open(p).convert('RGB'); red=blue=0
 for x in range(449,852):
  a,b,c=im.getpixel((x,72))
  red+=100<=a<=140 and b<45 and c<45
  blue+=100<=a<=140 and 100<=b<=140 and c>160
 rec={'label':n,'red':red,'blue':blue,'health_pct':round(100*(red+blue)/403,1)};print(rec,flush=True);r.append(rec)
cmd('setAIActive("shadowking","FALSE")','setCombatNode("shadowking","idle")')
time.sleep(33)
cmd('setInvulnerable("shadowking","FALSE")')
# Reset the isolated encounter's phase to 1 and its shield flag to off.
for bit in range(1,6):cmd(f'setGameFlag("x1v02",{bit},{int(bit==1)})')
cmd('setGameFlag("x1v01",27,0)')
B.fraction('shadowking',.8);time.sleep(1)
B.F.console('runscript astral/savepx/sk1pain');time.sleep(2)
shot('isolated_sk_shield_before')
B.teleport_party_to('shadowking');time.sleep(1);B.attack_burst(n=10,gap=.4);time.sleep(1);shot('isolated_sk_shield_after')
time.sleep(32);shot('isolated_sk_timer_before')
B.attack_burst(n=10,gap=.4);time.sleep(1);shot('isolated_sk_timer_after')
Path(B.OUT,'isolated_shadowking.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
