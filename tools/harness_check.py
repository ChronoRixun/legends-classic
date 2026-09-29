"""One-minute check of the xml2-fix background harness on a running --tour build (never touches focus).

usage: harness_check.py <out_dir_for_shots>
Waits for the game window, reports display mode / window style / foreground, drives New Game through the input
pipe while another window keeps the focus, then watches zone changes and grabs pipe screenshots.
"""
import ctypes
import ctypes.wintypes as w
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fixinput  # noqa: E402

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
TITLE = 'X-Men Legends 2'


class DEVMODEW(ctypes.Structure):
    _fields_ = [('dmDeviceName', w.WCHAR * 32), ('dmSpecVersion', w.WORD), ('dmDriverVersion', w.WORD),
                ('dmSize', w.WORD), ('dmDriverExtra', w.WORD), ('dmFields', w.DWORD), ('dmPositionX', w.LONG),
                ('dmPositionY', w.LONG), ('dmDisplayOrientation', w.DWORD), ('dmDisplayFixedOutput', w.DWORD),
                ('dmColor', w.SHORT), ('dmDuplex', w.SHORT), ('dmYResolution', w.SHORT), ('dmTTOption', w.SHORT),
                ('dmCollate', w.SHORT), ('dmFormName', w.WCHAR * 32), ('dmLogPixels', w.WORD),
                ('dmBitsPerPel', w.DWORD), ('dmPelsWidth', w.DWORD), ('dmPelsHeight', w.DWORD),
                ('dmDisplayFlags', w.DWORD), ('dmDisplayFrequency', w.DWORD), ('dmICMMethod', w.DWORD),
                ('dmICMIntent', w.DWORD), ('dmMediaType', w.DWORD), ('dmDitherType', w.DWORD),
                ('dmReserved1', w.DWORD), ('dmReserved2', w.DWORD), ('dmPanningWidth', w.DWORD),
                ('dmPanningHeight', w.DWORD)]


def display_mode():
    d = DEVMODEW()
    d.dmSize = ctypes.sizeof(DEVMODEW)
    u32.EnumDisplaySettingsW(None, 0xFFFFFFFF, ctypes.byref(d))
    return d.dmPelsWidth, d.dmPelsHeight, d.dmDisplayFrequency


def zone():
    return subprocess.run([sys.executable, os.path.join(HERE, 'current_zone.py')], capture_output=True,
                          text=True).stdout.strip().split(' ', 1)[-1]


def window_info(h):
    r, c = w.RECT(), w.RECT()
    u32.GetWindowRect(h, ctypes.byref(r))
    u32.GetClientRect(h, ctypes.byref(c))
    st = u32.GetWindowLongW(h, -16) & 0xffffffff
    ex = u32.GetWindowLongW(h, -20) & 0xffffffff
    return (f'rect {r.left},{r.top}-{r.right},{r.bottom} client {c.right}x{c.bottom} style 0x{st:08x} '
            f'caption={(st & 0x00C00000) == 0x00C00000} topmost={bool(ex & 8)}')


def log(msg):
    print(time.strftime('%H:%M:%S'), msg, flush=True)


def main(out):
    os.makedirs(out, exist_ok=True)
    log(f'desktop mode before: {display_mode()}')
    h = 0
    for _ in range(60):
        h = u32.FindWindowW(None, TITLE)
        if h:
            break
        time.sleep(1)
    if not h:
        log('no game window after 60 s')
        return 1
    time.sleep(3)
    log(f'window: {window_info(h)}')
    log(f'desktop mode with game up: {display_mode()}')
    # the harness never takes the focus: the owner's window should still be in front
    log(f'game is foreground: {u32.GetForegroundWindow() == h}')
    for _ in range(60):
        if fixinput.available():
            break
        time.sleep(1)
    log(f'pipe status: {fixinput.status() if fixinput.available() else "DOWN"}')
    t0 = time.time()
    while time.time() - t0 < 90 and 'main_back' not in zone():
        time.sleep(2)
    log(f'zone: {zone()} (menu reached after {time.time() - t0:.0f} s)')
    time.sleep(10)
    fixinput.screenshot(os.path.abspath(os.path.join(out, 'hc_menu.png')))
    log(f'game is foreground before keys: {u32.GetForegroundWindow() == h}')
    fixinput.key('enter')
    time.sleep(2.5)
    fixinput.key('enter')
    seen, t1 = [zone()], time.time()
    fg_changes = 0
    while time.time() - t1 < 45:
        if u32.GetForegroundWindow() == h:
            fg_changes += 1
        z = zone()
        if z != seen[-1]:
            seen.append(z)
            log(f'zone -> {z}')
        time.sleep(2)
    fixinput.screenshot(os.path.abspath(os.path.join(out, 'hc_zone.png')))
    log(f'zones seen: {seen}; polls with the game in front: {fg_changes}')
    log(f'game is foreground at the end: {u32.GetForegroundWindow() == h}; desktop mode: {display_mode()}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
