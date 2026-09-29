r"""Drive X-Men Legends II through xml2-fix's test input pipe - no window focus needed.

The game must run with xml2-fix's dinput.dll (branch display, 1.2.0+) and, in xml2-fix.ini next to it:
    [Test]
    InputPipe=1
tools/harness.py install writes that into a build, with [Display] Mode=windowed RunInBackground=1, so the game
sits in a small window and keeps running while the PC's owner works in other windows.

Several games at once: each build's game serves its own pipe ([Test] PipeName=<name>, harness.py install
--pipe-name <name>). This module talks to XML2FIX_PIPE=<name> (default xml2-fix-input); a tool that tests one
build calls use_build(<build>), which takes that build's pipe (and refuses an XML2FIX_PIPE naming another one).

The fix listens on \\.\pipe\xml2-fix-input: one command per line, one reply line each ("ok ..." or "error ..."):
    tap KEY [ms]         press and release (default 80 ms)
    hold KEY[+KEY] ms    hold together, then release
    down KEY / up KEY    hold until released (10 s at most - a dead client can't wedge a key)
    wm KEY [ms]          post WM_KEYDOWN / WM_KEYUP to the game window (xml2-fix 1.2.0+): what the Advanced
                         Options panel (Options > Controls > Advanced) reads - it never looks at DirectInput
    release              let go of everything
    screenshot PATH      save the frame the game just drew (.png or .bmp; give an absolute path)
    script STATEMENT     run an XML2 script statement: queued in the game's console as "runscript STATEMENT"
    console COMMAND      queue an engine console command as it is (loadmap nyc/alison/nyc1_1_3 1, ...)
    status | ping
KEY is a DirectInput name (RETURN, ESCAPE, W, UP, F1, NUMPAD4, ...) or scancode (0x1C); the gameinput.py names
(enter, esc, kp4, ...) are translated. Keys from the pipe reach the game whether or not it has the focus; the
real keyboard only counts while it does. Screenshots are copied from the Direct3D back buffer inside the game,
so they work with the window covered.

script / console (xml2-fix display branch after 1.2.0; older builds answer "error unknown command"): the line goes
into the game's own console queue (XMen2.exe 0x55c410, what loadMapKeepTeam uses) from inside the game's keyboard
read, on the game's thread. The reply "ok queued LINE" comes once it is in the queue; the game runs it at its NEXT
frame, so allow a frame or two before checking the effect. "error ..." = nothing was queued: the queue stayed full
for 2 s (it holds 2 commands), the game didn't read its keyboard for 2 s, or the line broke a rule:
  - 127 characters at most, "runscript " included (the queue keeps 127).
  - script: runscript takes ONE word (the console reads up to the first space or ';'), so the fix drops the spaces
    outside quotes - unlockCharacter("storm", "") is sent as runscript unlockCharacter("storm","") (the script
    tokenizer treats a space and a ',' alike; the game's own runscript lines have none). A string with a space in
    it, a ';' or a non-ASCII character can't go through: error. Quotes (' or ") pass as they are.
  - several statements on one line: join them with the four characters \n\r (backslash n backslash r; in Python
    r'a()\n\rb()'). No if/else (`if` needs a space after it) and no waittimed/waitsignal (runscript frees the
    code right after its first run).
  - text without '(' runs a script file: script menus/new_game = scripts/menus/new_game.py.
  - a statement the game can't compile (unknown function, wrong argument count or type) is dropped silently, as
    in a script file: check the effect (e.g. the team menu after unlockCharacter), not the reply.
  - no newlines in the text (one command per line); script()/console() refuse them.

Pads (xml2-fix branch pad-input): with [Test] VirtualPads=N (1-4) in xml2-fix.ini the game sees N Logitech Dual
Actions with nothing plugged in - virtual pad N is the game's pad N, i.e. player N's pad (pad 2 START = player 2
joins); they replace real controllers (XInput pad N's input goes into virtual pad N while the game has the focus).
Without VirtualPads the verbs reach the N-th real pad the fix presents. Pad verbs, N = 1-4:
    pad N BUTTON[+BUTTON] [ms]    press and release (80 ms)
    padhold N BUTTONS ms          hold together, then release
    paddown N BUTTONS [ms]        hold until padup (10 s at most)      padup N BUTTONS|ALL
    padrelease [N]                let go of everything on pad N (or every pad; "release" does keys and pads)
    stick N L|R X Y [ms]          stick at X,Y (-1..1, Y up): with ms held then centred (the reply waits);
                                  without, stays until the next stick command for it (0 0 lets go) or 10 s
    trigger N L|R VALUE [ms]      trigger at VALUE (0..1), the same way
BUTTON: A B X Y LB RB LT RT BACK START LS RS UP DOWN LEFT RIGHT (Xbox names; LT/RT pull the trigger all the way),
through the fix's Dual Action layout: A = Attack / menu accept, B = Smash / menu back, START = Pause / join.
A tap or timed hold answers once the game has read the pad meanwhile; "error ..." if it didn't (no such pad).

usage: fixinput.py key enter|esc|up|down|left|right|space|<letter> [count]
       fixinput.py hold w+d 1.5
       fixinput.py down w | up w | release
       fixinput.py wm down [count]      (the Advanced Options panel: up/down move, left/right/enter cycle, esc backs out)
       fixinput.py screenshot out.png
       fixinput.py script 'unlockCharacter("storm", "")'
       fixinput.py console loadmap nyc/alison/nyc1_1_3 1
       fixinput.py status
       fixinput.py check                (is the pipe up? exit code 0 = yes)
       fixinput.py pad 1 a [count]      (pad 1's A; pad 2 start = player 2 joins)
       fixinput.py padhold 2 lb+y 0.5
       fixinput.py paddown 1 rt | padup 1 rt | padrelease [2]
       fixinput.py stick 1 l 0 1 [seconds]     (left stick up; without seconds it stays: stick 1 l 0 0 lets go)
       fixinput.py trigger 2 r 1 [seconds]
Same call shapes as gameinput.py: key(name, hold), hold(names, seconds), plus screenshot(path), wm(names, hold),
script(statement) and console(command); pads: pad(n, buttons, hold), padhold(n, buttons, seconds),
paddown(n, buttons), padup(n, buttons), padrelease(n), stick(n, side, x, y, seconds), trigger(n, side, value, seconds).
gameinput.py uses this module whenever the pipe is up (XML1_INPUT=pipe forces it, XML1_INPUT=sendinput the old way).
"""
import ctypes
import ctypes.wintypes as w
import os
import sys
import time

# A second game instance serves its own pipe ([Test] PipeName= in its xml2-fix.ini); XML2FIX_PIPE picks it, and
# use_build(<build>) points a tool at the pipe of the build it tests (see there).
DEFAULT_PIPE_NAME = 'xml2-fix-input'
PIPE = '\\\\.\\pipe\\' + (os.environ.get('XML2FIX_PIPE') or DEFAULT_PIPE_NAME)

# gameinput.py's key names -> DirectInput names; anything else goes through as typed (upper-cased).
NAMES = {'esc': 'ESCAPE', 'enter': 'RETURN', 'space': 'SPACE', 'up': 'UP', 'down': 'DOWN', 'left': 'LEFT',
         'right': 'RIGHT', 'tab': 'TAB', 'kp4': 'NUMPAD4', 'kp6': 'NUMPAD6', 'kp8': 'NUMPAD8', 'kp2': 'NUMPAD2',
         '10': '0', 'backspace': 'BACK', 'del': 'DELETE', 'pgup': 'PRIOR', 'pgdn': 'NEXT', 'shift': 'LSHIFT',
         'ctrl': 'LCONTROL', 'alt': 'LMENU'}

k32 = ctypes.windll.kernel32
k32.CreateFileW.restype = w.HANDLE
k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
k32.WriteFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
k32.ReadFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
k32.CloseHandle.argtypes = [w.HANDLE]
k32.WaitNamedPipeW.argtypes = [w.LPCWSTR, w.DWORD]

GENERIC_READ, GENERIC_WRITE, OPEN_EXISTING = 0x80000000, 0x40000000, 3
INVALID_HANDLE = w.HANDLE(-1).value
ERROR_FILE_NOT_FOUND, ERROR_SEM_TIMEOUT, ERROR_PIPE_BUSY = 2, 121, 231


class PipeDown(SystemExit):
    """The pipe isn't there (game not running, or [Test] InputPipe=1 missing). A SystemExit like
    gameinput.focus()'s "window not found", so callers that catch that keep working."""


class PipeError(RuntimeError):
    """The fix answered "error ..."."""


def available():
    """True when the game is running with the pipe on."""
    if k32.WaitNamedPipeW(PIPE, 50):
        return True
    return k32.GetLastError() in (ERROR_SEM_TIMEOUT, ERROR_PIPE_BUSY)  # exists, busy with another client


class Pipe:
    def __init__(self, timeout=5.0):
        self.handle = None
        self.timeout = timeout

    def connect(self):
        deadline = time.time() + self.timeout
        while True:
            handle = k32.CreateFileW(PIPE, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
            if handle != INVALID_HANDLE:
                self.handle = handle
                return
            err = k32.GetLastError()
            if err == ERROR_PIPE_BUSY and time.time() < deadline:
                k32.WaitNamedPipeW(PIPE, 1000)  # another client is on it; the fix takes one at a time
                continue
            if err == ERROR_FILE_NOT_FOUND:
                raise PipeDown(f'{PIPE} is not up: is the game running with xml2-fix and [Test] InputPipe=1?')
            raise PipeDown(f'cannot open {PIPE} (error {err})')

    def close(self):
        if self.handle is not None:
            k32.CloseHandle(self.handle)
            self.handle = None

    def ask(self, line):
        """One command line -> the reply text ("ok ..."); raises PipeError on "error ...", PipeDown if the pipe went."""
        if self.handle is None:
            self.connect()
        data = (line.rstrip('\r\n') + '\n').encode('utf-8')
        written = w.DWORD()
        if not k32.WriteFile(self.handle, data, len(data), ctypes.byref(written), None):
            self.close()
            raise PipeDown(f'writing to {PIPE} failed (error {k32.GetLastError()}) - did the game exit?')
        reply = b''
        buf = ctypes.create_string_buffer(512)
        got = w.DWORD()
        while b'\n' not in reply:
            if not k32.ReadFile(self.handle, buf, 512, ctypes.byref(got), None) or got.value == 0:
                self.close()
                raise PipeDown(f'{PIPE} closed - did the game exit?')
            reply += buf.raw[:got.value]
        text = reply.split(b'\n', 1)[0].decode('utf-8', 'replace').strip()
        if text.startswith('error'):
            raise PipeError(text)
        return text


_pipe = None


def pipe():
    global _pipe
    if _pipe is None:
        _pipe = Pipe()
    return _pipe


def pipe_name():
    """The name of the pipe this process talks to (the part after \\\\.\\pipe\\)."""
    return PIPE.rsplit('\\', 1)[-1]


def pipe_name_for(folder):
    """The test pipe the game in `folder` serves: [Test] PipeName of <folder>\\xml2-fix.ini (DEFAULT_PIPE_NAME when
    it has none), or None when there is no ini or no [Test] InputPipe=1 (a play build: no pipe)."""
    import configparser
    cp = configparser.ConfigParser(strict=False, interpolation=None, comment_prefixes=(';', '#'))
    try:
        if not cp.read(os.path.join(folder, 'xml2-fix.ini'), encoding='latin-1'):
            return None
        if cp.get('Test', 'InputPipe', fallback='0').strip() != '1':
            return None
        return cp.get('Test', 'PipeName', fallback='').strip() or DEFAULT_PIPE_NAME
    except (configparser.Error, OSError, UnicodeError):
        return None


def use_build(build):
    """Talk to the pipe that <build>'s game serves, so a tool testing one build never drives another folder's game.

    XML2FIX_PIPE unset: the build's own pipe (its xml2-fix.ini [Test] PipeName, e.g. from harness.py install
    --pipe-name; the default pipe without one) - no variable needed. XML2FIX_PIPE set: it must name that pipe, else
    SystemExit (the variable points at another game's pipe). Returns the pipe name, or None when the build has no
    pipe harness (nothing changes then)."""
    global PIPE, _pipe
    name = pipe_name_for(build)
    if name is None:
        return None
    env = os.environ.get('XML2FIX_PIPE')
    if env and env.lower() != name.lower():
        raise SystemExit(f'XML2FIX_PIPE={env}, but {os.path.join(build, "xml2-fix.ini")} serves the pipe "{name}": '
                         f'that variable points at another game. Set XML2FIX_PIPE={name} or leave it unset.')
    new = '\\\\.\\pipe\\' + name
    if new.lower() != PIPE.lower():
        if _pipe is not None:
            _pipe.close()
            _pipe = None
        PIPE = new
    return name


def dik(name):
    name = str(name)
    return NAMES.get(name.lower(), name.upper())


def key(name, hold=0.08):
    """Press and release one key (a gameinput.py name, a DirectInput name or a scancode)."""
    return pipe().ask(f'tap {dik(name)} {int(round(hold * 1000))}')


def taps(names, gap=0.25, hold=0.08):
    """A sequence of single presses, e.g. taps(['enter', 'enter', 'down'])."""
    for n in names:
        key(n, hold)
        time.sleep(gap)


def hold(names, seconds):
    """Hold keys together for `seconds`, e.g. hold('w+d', 1.5) or hold(['w', 'd'], 1.5)."""
    if isinstance(names, str):
        names = names.split('+')
    return pipe().ask(f'hold {"+".join(dik(n) for n in names)} {int(round(seconds * 1000))}')


def down(names):
    if isinstance(names, str):
        names = names.split('+')
    return pipe().ask(f'down {"+".join(dik(n) for n in names)}')


def up(names):
    if isinstance(names, str):
        names = names.split('+')
    return pipe().ask(f'up {"+".join(dik(n) for n in names)}')


def release():
    return pipe().ask('release')


def wm(names, hold=0.08):
    """Post Win32 key messages (WM_KEYDOWN, then WM_KEYUP after `hold` seconds) for the keys to the game window.

    The game's Advanced Options panel is the one screen that reads Windows key messages instead of DirectInput,
    so key()/tap can't drive it and this can: wm('down') moves the selection, wm('right') / wm('enter') cycle a
    row's value, wm('esc') backs out. Works with the window in the background. Needs xml2-fix 1.2.0 or later."""
    if isinstance(names, str):
        names = names.split('+')
    return pipe().ask(f'wm {"+".join(dik(n) for n in names)} {int(round(hold * 1000))}')


def screenshot(path):
    """Save the frame the game just drew to `path` (.png or .bmp). Returns the absolute path."""
    path = os.path.abspath(path)
    pipe().ask(f'screenshot {path}')
    return path


def _one_line(text):
    text = str(text).strip()
    if '\n' in text or '\r' in text:
        raise ValueError('one command per line: no newlines in a script statement or console command '
                         r'(join statements with the four characters \n\r instead)')
    return text


def script(statement):
    """Run an XML2 script statement in the game, e.g. script('unlockCharacter("storm", "")').

    Returns the reply, "ok queued runscript unlockCharacter("storm","")" (spaces outside quotes dropped: see the
    module docstring); raises PipeError if nothing was queued. The game runs it at its next frame, and one it
    can't compile is dropped without a word, so check the effect."""
    return pipe().ask(f'script {_one_line(statement)}')


def console(command):
    """Queue an engine console command as it is, e.g. console('loadmap nyc/alison/nyc1_1_3 1').

    Returns the reply, "ok queued <command>"; raises PipeError if nothing was queued. Runs at the game's next frame."""
    return pipe().ask(f'console {_one_line(command)}')


def _buttons(buttons):
    """'a+start', 'A', ['a', 'start'] -> 'A+START'."""
    if isinstance(buttons, str):
        buttons = buttons.split('+')
    return '+'.join(str(b).strip().upper() for b in buttons)


def _ms(seconds):
    return int(round(seconds * 1000))


def pad(n, buttons, hold=0.08):
    """Press and release buttons on pad n (1-4), e.g. pad(1, 'a'), pad(2, 'start'), pad(1, 'lb+a', 0.3).

    With xml2-fix's [Test] VirtualPads the game sees virtual pad n as its pad n: player n's pad, so pad(2, 'start')
    is player 2 joining. Returns after the release, once the game has read the pad; PipeError if it never did."""
    return pipe().ask(f'pad {int(n)} {_buttons(buttons)} {_ms(hold)}')


def padhold(n, buttons, seconds):
    """Hold buttons on pad n together for `seconds`, then release, e.g. padhold(1, 'rt+a', 0.5)."""
    return pipe().ask(f'padhold {int(n)} {_buttons(buttons)} {_ms(seconds)}')


def paddown(n, buttons):
    """Hold buttons on pad n until padup()/padrelease() (10 s at most)."""
    return pipe().ask(f'paddown {int(n)} {_buttons(buttons)}')


def padup(n, buttons='all'):
    """Let go of buttons on pad n; padup(n) lets go of everything on it (sticks and triggers too)."""
    return pipe().ask(f'padup {int(n)} {_buttons(buttons)}')


def padrelease(n=None):
    """Let go of everything on pad n, or on every pad."""
    return pipe().ask('padrelease' if n is None else f'padrelease {int(n)}')


def _side(side):
    side = str(side).strip().upper()[:1]
    if side not in ('L', 'R'):
        raise ValueError(f'side must be L or R, not {side!r}')
    return side


def stick(n, side, x, y, seconds=None):
    """Put pad n's left ('l') or right ('r') stick at x, y (-1..1, y up).

    With `seconds` it is held that long, then centred, and this returns after that; without, it stays until the next
    stick() for that stick (stick(n, side, 0, 0) lets go), padup(n) or 10 s."""
    line = f'stick {int(n)} {_side(side)} {float(x):g} {float(y):g}'
    return pipe().ask(line if seconds is None else f'{line} {_ms(seconds)}')


def trigger(n, side, value, seconds=None):
    """Pull pad n's left ('l') or right ('r') trigger to `value` (0..1); `seconds` as for stick()."""
    line = f'trigger {int(n)} {_side(side)} {float(value):g}'
    return pipe().ask(line if seconds is None else f'{line} {_ms(seconds)}')


def status():
    return pipe().ask('status')


def check(verbose=True):
    """Self-check: is the pipe up, and does the game read its keyboard? Prints and returns True/False."""
    if not available():
        if verbose:
            print(f'pipe down: {PIPE} is not there (game not running, or [Test] InputPipe=1 missing in xml2-fix.ini)')
        return False
    try:
        text = status()
    except (PipeDown, PipeError) as e:
        if verbose:
            print(f'pipe up but not answering: {e}')
        return False
    if verbose:
        print(f'pipe up: {text}')
        if 'keyboard devices 0' in text:
            print('  the game has not created its keyboard device yet (still starting?) - keys will not land until it does')
    return True


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == 'check':
        return 0 if check() else 1
    if cmd == 'status':
        print(status())
    elif cmd == 'key':
        for _ in range(int(argv[2]) if len(argv) > 2 else 1):
            key(argv[1])
            time.sleep(0.25)
    elif cmd == 'hold':
        hold(argv[1], float(argv[2]))
    elif cmd == 'down':
        down(argv[1])
    elif cmd == 'up':
        up(argv[1])
    elif cmd == 'release':
        release()
    elif cmd == 'wm':
        for _ in range(int(argv[2]) if len(argv) > 2 else 1):
            wm(argv[1])
            time.sleep(0.25)
    elif cmd == 'screenshot':
        print(screenshot(argv[1]))
    elif cmd == 'script':
        print(script(' '.join(argv[1:])))
    elif cmd == 'console':
        print(console(' '.join(argv[1:])))
    elif cmd == 'pad':
        for _ in range(int(argv[3]) if len(argv) > 3 else 1):
            pad(argv[1], argv[2])
            time.sleep(0.25)
    elif cmd == 'padhold':
        padhold(argv[1], argv[2], float(argv[3]))
    elif cmd == 'paddown':
        paddown(argv[1], argv[2])
    elif cmd == 'padup':
        padup(argv[1], argv[2] if len(argv) > 2 else 'all')
    elif cmd == 'padrelease':
        padrelease(argv[1] if len(argv) > 1 else None)
    elif cmd == 'stick':
        stick(argv[1], argv[2], float(argv[3]), float(argv[4]), float(argv[5]) if len(argv) > 5 else None)
    elif cmd == 'trigger':
        trigger(argv[1], argv[2], float(argv[3]), float(argv[4]) if len(argv) > 4 else None)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except PipeError as e:
        sys.exit(str(e))
