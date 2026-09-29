"""Send key presses / mouse clicks to the XML2 window.

Two backends:
  - xml2-fix input pipe (tools/fixinput.py): the game runs with xml2-fix's dinput.dll and [Test] InputPipe=1
    (tools/harness.py install). Keys go straight into the game's DirectInput keyboard, no focus needed, so the
    PC's owner keeps the foreground. Used whenever the pipe is up; XML1_INPUT=pipe insists on it.
  - SendInput scancodes (the old way): forces the game window to the foreground first. XML1_INPUT=sendinput.
Mouse clicks always use SendInput (the pipe has no mouse), so `click` still takes the focus.

usage: gameinput.py key enter|esc|up|down|left|right|space|<letter> [count]
       gameinput.py hold w+d 1.5
       gameinput.py click X Y
       gameinput.py wait-title   (just focus the window; nothing with the pipe)
"""
import ctypes, ctypes.wintypes as w, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fixinput  # noqa: E402

user32 = ctypes.windll.user32
TITLE = 'X-Men Legends 2'
SCAN = {'esc': 0x01, 'enter': 0x1C, 'space': 0x39, 'up': (0x48, True), 'down': (0x50, True),
        'left': (0x4B, True), 'right': (0x4D, True), 'tab': 0x0F, 'kp4': 0x4B, 'kp6': 0x4D, 'kp8': 0x48, 'kp2': 0x50,
        **{c: s for c, s in zip('qwertyuiop', range(0x10, 0x1A))},
        **{c: s for c, s in zip('asdfghjkl', range(0x1E, 0x27))},
        **{c: s for c, s in zip('zxcvbnm', range(0x2C, 0x33))},
        **{str(n): 0x02 + (n - 1) % 10 for n in range(1, 11)}}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', w.WORD), ('wScan', w.WORD), ('dwFlags', w.DWORD), ('time', w.DWORD),
                ('dwExtraInfo', ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', w.LONG), ('dy', w.LONG), ('mouseData', w.DWORD), ('dwFlags', w.DWORD),
                ('time', w.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT), ('pad', ctypes.c_byte * 32)]
    _anonymous_ = ('u',)
    _fields_ = [('type', w.DWORD), ('u', _U)]


def send(inp):
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def use_pipe():
    """Key presses go through xml2-fix's pipe: XML1_INPUT=pipe forces it, XML1_INPUT=sendinput forces the old
    SendInput path, otherwise (auto) the pipe is used whenever it is up."""
    mode = os.environ.get('XML1_INPUT', 'auto').lower()
    if mode == 'pipe':
        return True
    if mode in ('sendinput', 'focus', 'foreground'):
        return False
    return fixinput.available()


def find_window():
    return user32.FindWindowW(None, TITLE)


def focus(force=False):
    """Bring the game window to the front - only for SendInput (or force=True, which clicks need). With the pipe
    this never calls SetForegroundWindow/AttachThreadInput: the PC's owner keeps the foreground."""
    hwnd = find_window()
    if use_pipe() and not force:
        return hwnd
    if not hwnd:
        raise SystemExit(f'window "{TITLE}" not found')
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    if user32.GetForegroundWindow() != hwnd:
        # Windows only lets the focused app hand focus over: attach to its input thread and
        # bounce through topmost so the game window really comes to the front
        k32 = ctypes.windll.kernel32
        fg = user32.GetForegroundWindow()
        tid_fg = user32.GetWindowThreadProcessId(fg, None)
        tid_me = k32.GetCurrentThreadId()
        user32.AttachThreadInput(tid_me, tid_fg, True)
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
        user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.AttachThreadInput(tid_me, tid_fg, False)
    time.sleep(0.3)
    return hwnd


def _scan(name):
    code = SCAN[name.lower()]
    if isinstance(code, tuple):
        return code[0], 1
    return code, 0


def key(name, hold=0.08):
    if use_pipe():
        try:
            fixinput.key(name, hold)
        except fixinput.PipeError as e:
            raise SystemExit(str(e))  # the press didn't land (the game isn't polling, e.g. while loading) - like "window not found"
        return
    code, ext = _scan(name)
    for up in (0, 2):
        i = INPUT(type=1)
        i.ki = KEYBDINPUT(0, code, 0x0008 | up | ext, 0, 0)  # KEYEVENTF_SCANCODE
        send(i)
        time.sleep(hold)


def hold(names, seconds):
    """Hold one or more keys together, e.g. hold('w+d', 1.5) or hold(['w', 'd'], 1.5)."""
    if isinstance(names, str):
        names = names.split('+')
    if use_pipe():
        try:
            fixinput.hold(names, seconds)
        except fixinput.PipeError as e:
            raise SystemExit(str(e))
        return
    for n in names:
        code, ext = _scan(n)
        i = INPUT(type=1)
        i.ki = KEYBDINPUT(0, code, 0x0008 | ext, 0, 0)
        send(i)
    time.sleep(seconds)
    for n in names:
        code, ext = _scan(n)
        i = INPUT(type=1)
        i.ki = KEYBDINPUT(0, code, 0x0008 | 0x0002 | ext, 0, 0)
        send(i)


def click(x, y):
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    i = INPUT(type=0)
    i.mi = MOUSEINPUT(int(x * 65535 / (sw - 1)), int(y * 65535 / (sh - 1)), 0, 0x8001, 0, 0)
    send(i)
    time.sleep(0.15)
    for flag in (0x0002, 0x0004):
        i = INPUT(type=0)
        i.mi = MOUSEINPUT(0, 0, 0, flag, 0, 0)
        send(i)
        time.sleep(0.08)


if __name__ == '__main__':
    cmd = sys.argv[1]
    focus(force=cmd == 'click')
    if cmd == 'key':
        for _ in range(int(sys.argv[3]) if len(sys.argv) > 3 else 1):
            key(sys.argv[2])
            time.sleep(0.25)
    elif cmd == 'hold':
        hold(sys.argv[2], float(sys.argv[3]))
    elif cmd == 'click':
        click(int(sys.argv[2]), int(sys.argv[3]))
