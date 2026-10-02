"""Issue 2 controlled phase checks using the supplied boss_common harness helpers.
Outputs stay outside Git. Run with BOSS_BUILD and BOSS_OUT pointing at the isolated installation.
"""
import json, os, pathlib, sys, time, ctypes
import boss_common as B
from current_zone import proc_path
assert pathlib.Path(proc_path(B.PID)).parent == pathlib.Path(B.BUILD)
# A minimized D3D window yields stale captures. Restore without activation.
hwnd=B.game_hwnd()
if hwnd: ctypes.windll.user32.ShowWindow(hwnd,4)
case=sys.argv[1]
B.LOGFILE=os.path.join(B.OUT,case+'.log')
results=[]
def sample(label):
 p=B.shot(label);
 from PIL import Image
 im=Image.open(p).convert('RGB');red=blue=0
 for x in range(449,852):
  a,b,c=im.getpixel((x,72));red+=100<=a<=140 and b<45 and c<45;blue+=100<=a<=140 and 100<=b<=140 and c>160
 r={'label':label,'bar':round(100*(red+blue)/403,1),'blue_pixels':blue,'zone':B.zone()};results.append(r);B.log(r);return r

def command(*lines):
 B.script(*lines);time.sleep(.4)

def hit(boss,label,n=8):
 command(f'setDefaultTarget("{boss}")')
 B.teleport_party_to(boss);time.sleep(1.3)
 command(f'x=getPosX("{boss}")', 'x=iadd(x,150)', 'setPosX("_HERO1_",x)')
 command(f'faceEntity("_HERO1_","{boss}")')
 sample(label+'_before');B.attack_burst('NUMPAD6',n,gap=.45);time.sleep(1);sample(label+'_after')

def fresh(zone):
 if B.zone().startswith('menu'):B.new_game()
 B.seat('wolverine','cyclops','storm','iceman');time.sleep(1)
 B.goto(zone,settle=15)
 B.shot('loaded_'+case)                 # successful fresh frame is required, not a message-pump heuristic
 B.invulnerable(True);time.sleep(1)
 # Keep other heroes from contributing damage during measurements.
 for i in (2,3,4):command(f'setAIActive("_HERO{i}_","FALSE")')

if case=='magneto':
 fresh('astroid_m/visit1/asteroid2_1')
 command('act("trigger_touch06","trigger_touch06")');time.sleep(2)
 for i in range(9):B.F.key('RETURN');time.sleep(1.5)
 command('setDefaultTarget("magneto")')
 hit('magneto','mag_initial')
 command('act("shieldup","shieldup")');time.sleep(2)
 hit('magneto','mag_shield')
 # Stage2 is a four-input relay, counting the pain trigger and three acolyte deaths.
 for i in range(4):command('act("stage2","stage2")')
 time.sleep(3);hit('magneto','mag_stage2')
elif case=='mastermold':
 fresh('mastermold/mastermold2');hit('mastermold','mm_shield',n=24)
 # Destroy the actual cores first, then use the actual switches; this exercises their scripts.
 for i in (1,2,3):command(f'damage("warp{i}","_HERO1_",100000)');time.sleep(1)
 for i in (1,2,3):command(f'act("warpcore_switch0{i}","warpcore_switch0{i}")');time.sleep(2)
 time.sleep(9);hit('mastermold','mm_cores_complete',n=24)
elif case=='shadowking':
 fresh('astral/savepx/final_astral')
 hit('shadowking','sk_initial')
 # Force only the threshold; a real hero hit must invoke the pain script and start the timer.
 B.fraction('shadowking',.80);time.sleep(1)
 hit('shadowking','sk_threshold')
 hit('shadowking','sk_shield')
 time.sleep(32)
 hit('shadowking','sk_timer_expired')
else:raise ValueError(case)
path=pathlib.Path(B.OUT)/(case+'.json');path.write_text(json.dumps(results,indent=2),encoding='utf-8')
print('RESULT',path,flush=True)
