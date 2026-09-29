"""Probe whether XMen2.exe (windowed) keeps running unfocused / minimised, and whether PrintWindow captures it.

usage: bg_probe.py <results_png_prefix>
Assumes the game is already at a --tour build's first zone (zones auto-advance every ~12 s, so zone
changes prove the simulation runs). Reads the zone from memory (current_zone.py), never touches the keyboard.
"""
import ctypes, ctypes.wintypes as w, subprocess, sys, time, os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
u32.SetProcessDPIAware()
TITLE = 'X-Men Legends 2'
HWND_BOTTOM, SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 1, 1, 2, 0x10
SW_MINIMIZE, SW_RESTORE = 6, 9
PW_RENDERFULLCONTENT = 2


def zone():
    return subprocess.run([sys.executable, os.path.join(HERE, 'current_zone.py')], capture_output=True,
                          text=True).stdout.strip().split(' ', 1)[-1]


def watch(label, seconds=40):
    seen, t0 = [], time.time()
    while time.time() - t0 < seconds:
        z = zone()
        if not seen or seen[-1] != z:
            seen.append(z)
        time.sleep(3)
    print(f'{label}: {len(seen) - 1} zone changes in {seconds}s: {seen}', flush=True)
    return len(seen) - 1


def printwindow(hwnd, path):
    r = w.RECT()
    u32.GetClientRect(hwnd, ctypes.byref(r))
    wd, ht = r.right - r.left, r.bottom - r.top
    hdc = u32.GetDC(0)
    mdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, wd, ht)
    g32.SelectObject(mdc, bmp)
    ok = u32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT)

    class BMI(ctypes.Structure):
        _fields_ = [('biSize', w.DWORD), ('biWidth', w.LONG), ('biHeight', w.LONG), ('biPlanes', w.WORD),
                    ('biBitCount', w.WORD), ('biCompression', w.DWORD), ('biSizeImage', w.DWORD),
                    ('biXPelsPerMeter', w.LONG), ('biYPelsPerMeter', w.LONG), ('biClrUsed', w.DWORD),
                    ('biClrImportant', w.DWORD)]
    bmi = BMI(ctypes.sizeof(BMI), wd, -ht, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(wd * ht * 4)
    g32.GetDIBits(mdc, bmp, 0, ht, buf, ctypes.byref(bmi), 0)
    img = Image.frombuffer('RGBA', (wd, ht), buf.raw, 'raw', 'BGRA', 0, 1).convert('RGB')
    img.save(path)
    px = list(img.resize((32, 32)).getdata())
    nonblack = sum(1 for p in px if max(p) > 24)
    print(f'PrintWindow ok={ok} {wd}x{ht} -> {path}: {nonblack}/1024 sample pixels non-black', flush=True)
    g32.DeleteObject(bmp); g32.DeleteDC(mdc); u32.ReleaseDC(0, hdc)


def main(prefix):
    hwnd = u32.FindWindowW(None, TITLE)
    if not hwnd:
        print('game window not found'); return
    print('game hwnd', hwnd, 'foreground', u32.GetForegroundWindow() == hwnd, flush=True)
    watch('focused baseline', 30)
    # 1. behind everything, another window active (the desktop shell)
    u32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
    shell = u32.FindWindowW('Progman', None)
    u32.SetForegroundWindow(shell)
    time.sleep(1)
    print('foreground is game:', u32.GetForegroundWindow() == hwnd, flush=True)
    watch('unfocused (bottom of z-order)', 40)
    printwindow(hwnd, prefix + '_unfocused.png')
    # 2. minimised
    u32.ShowWindow(hwnd, SW_MINIMIZE)
    time.sleep(1)
    print('minimised:', bool(u32.IsIconic(hwnd)), flush=True)
    watch('minimised', 40)
    printwindow(hwnd, prefix + '_minimised.png')
    u32.ShowWindow(hwnd, SW_RESTORE)
    time.sleep(1)
    watch('restored (not focused)', 20)


if __name__ == '__main__':
    main(sys.argv[1])
