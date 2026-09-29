"""Scan an executable image for script-function registration tables.

Entry layout (verified in XMen2.exe: entry @0x68af88 = {0x4a5db0, "getGameFlag", "i", "si"};
0x4a5db0 reads arg0 via vtbl+0x14 (string) and arg1 via vtbl+0x10 (int) and returns a value):
    +0 void *func, +4 char *name, +8 char *ret_sig, +12 char *arg_sig (may be NULL = no args)
Scans every 4-aligned dword for that shape and exports all matches as JSON.
Usage: scan_functable.py <exe> <out.json>
"""
import sys, re, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from binimg import Image

ID = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*|==|!=|<=|>=|<|>|\+|-|\*|/|%|&&|\|\||!|&|\||=)$')
SIG = re.compile(r'^[a-z]*$')

img = Image(sys.argv[1])
lo, hi = img.text
found = []
mem = img.mem
for off in range(0, len(mem) - 16, 4):
    va = img.base + off
    f, n, r, a = img.u32(va), img.u32(va + 4), img.u32(va + 8), img.u32(va + 12)
    if not (lo <= f < hi):
        continue
    if not (img.ok(n) and img.ok(r)):
        continue
    rs = img.cstr(r, 8)
    if rs is None or len(rs) != 1 or not SIG.match(rs):
        continue
    if a == 0:
        asg = ''
    else:
        if not img.ok(a):
            continue
        asg = img.cstr(a, 32)
        if asg is None or not SIG.match(asg):
            continue
    ns = img.cstr(n, 64)
    if ns is None or not ID.match(ns):
        continue
    found.append({'entry': va, 'name': ns, 'ret': rs, 'args': asg, 'func': f})

runs = []
for e in found:
    if runs and e['entry'] - runs[-1][-1]['entry'] == 16:
        runs[-1].append(e)
    else:
        runs.append([e])
for i, run in enumerate(runs):
    print(f"table run {i} @ {run[0]['entry']:08x}..{run[-1]['entry'] + 16:08x}: {len(run)} entries "
          f"(first {run[0]['name']}, last {run[-1]['name']})")
    for e in run:
        e['table'] = f"{run[0]['entry']:08x}"
print('total', len(found))
json.dump([{**e, 'entry': hex(e['entry']), 'func': hex(e['func'])} for e in found],
          open(sys.argv[2], 'w'), indent=1)
