import sys,time,json,os
from pathlib import Path
import boss_common as B
from PIL import Image
records=[]
def snap(n):
 p=B.shot(n);im=Image.open(p).convert('RGB');red=blue=0
 for x in range(449,852):
  r,g,b=im.getpixel((x,72));red+=100<=r<=140 and g<45 and b<45;blue+=100<=r<=140 and 100<=g<=140 and b>160
 d=dict(label=n,red=red,blue=blue,health_pct=round(100*(red+blue)/403,1));records.append(d);print(d,flush=True)
B.fraction('shadowking',.65);time.sleep(1);B.attack_burst(n=3);time.sleep(1)
snap('sk_protected_confirmed_before');B.attack_burst(n=10);time.sleep(1);snap('sk_protected_confirmed_after')
time.sleep(32);snap('sk_unprotected_confirmed_before');B.attack_burst(n=10);time.sleep(1);snap('sk_unprotected_confirmed_after')
# Set up the last damage window, then use a hero attack for the phase-ending hit.
B.script('setInvulnerable("shadowking","FALSE")');time.sleep(.5)
for bit in range(1,6):B.script(f'setGameFlag("x1v02",{bit},{(6 >> (bit-1)) & 1})');time.sleep(.4)
B.script('setGameFlag("x1v01",27,0)','setHealth("shadowking",1)');time.sleep(1)
B.attack_burst(n=12);time.sleep(4);snap('sk_phase1_ordinary_hit_finish')
Path(B.OUT,'shadowking_confirmed.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
