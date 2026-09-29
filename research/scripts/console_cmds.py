"""Extract console-command registrations.
Pattern: call <getter> ... push <handler> ; push "name" ... call dword ptr [reg + <off>]  (within 8 lines)
Usage: console_cmds.py <asm listing> <getter-hex> <vtbl-off-hex>"""
import sys, re
lines = open(sys.argv[1], encoding='utf-8').read().splitlines()
getter = 'call 0x' + sys.argv[2]
off = sys.argv[3]
callre = re.compile(r'call dword ptr \[e[a-d]x \+ ' + off + r'\]$')
out = []
for i, l in enumerate(lines):
    if not callre.search(l):
        continue
    win = lines[max(0, i - 8):i]
    if not any(w.endswith(getter) for w in win):
        continue
    name = handler = None
    for w in win:
        m = re.match(r'([0-9a-f]+) push 0x([0-9a-f]+) ; "(.*)"', w)
        if m:
            name = m.group(3)
        m2 = re.match(r'([0-9a-f]+) push 0x([0-9a-f]{5,8})$', w)
        if m2:
            handler = m2.group(2)
    if name:
        out.append((name, handler, l.split()[0]))
for n, h, a in sorted(set(out)):
    print(f'{n:32} handler 0x{h}  (reg @ {a})')
print(len(set(out)), 'commands')
