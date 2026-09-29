r"""Read the zone name XMen2.exe is loading/running from its fixed global buffer (0x72a758), and find the game.

usage: current_zone.py [<build_dir>]     (prints pid and zone once; with a build, only that build's game)
Found from a crash register dump: EDI -> "menu/main_back" at 0x0072a758 during zone load.

Which XMen2.exe: several can run at once (a second test window, other agents' builds, Owen's play build), so no
tool takes "the first XMen2.exe" or kills by image name:
  game_pid(build)      the XMen2.exe started from <build>\XMen2.exe (folders compared with junctions resolved and
                       case folded); None if that build's game is not running. The test tools pass their build.
  game_pid()           no build: the only XMen2.exe when one runs (as before). With several, the one whose folder's
                       xml2-fix.ini serves the pipe this process talks to ([Test] PipeName = XML2FIX_PIPE; no
                       PipeName = the default pipe, fixinput.py); None (and a note on stderr) unless exactly one does.
  build_pids(build)    every XMen2.exe of <build>;  kill_build(build) ends those (taskkill /PID, never /IM) and waits.
  running()            [(pid, exe path)] of every XMen2.exe.
The read-only probes (actor_slots.py, conv_probe.py, hero_xp.py) take --build DIR for the same choice.
"""
import ctypes
import ctypes.wintypes as w
import os
import subprocess
import sys
import time

ZONE_ADDR = 0x0072A758
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = w.HANDLE
k32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
k32.CloseHandle.argtypes = [w.HANDLE]
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def proc_path(pid):
    """The full path of the process's image, or None (gone, or not ours to open)."""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = w.DWORD(len(buf))
        return buf.value if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else None
    finally:
        k32.CloseHandle(h)


def running():
    """[(pid, exe path or None)] of every running XMen2.exe, in tasklist order."""
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq XMen2.exe', '/FO', 'CSV', '/NH'],
                         capture_output=True, text=True).stdout
    procs = []
    for line in out.splitlines():
        parts = line.strip('"').split('","')
        if len(parts) > 1 and parts[0].lower() == 'xmen2.exe':
            pid = int(parts[1])
            procs.append((pid, proc_path(pid)))
    return procs


def same_folder(a, b):
    """Two folder paths name the same folder: absolute, junctions / symlinks resolved, case folded."""
    if not a or not b:
        return False
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def in_build(exe, build):
    """The exe is <build>\\XMen2.exe (the game of that build folder)."""
    return bool(exe) and same_folder(os.path.dirname(exe), build)


def build_pids(build):
    return [pid for pid, exe in running() if in_build(exe, build)]


_noted = set()


def game_pid(build=None):
    """The XMen2.exe under test (see the module docstring); None if it is not running (or, without a build, not
    known for sure)."""
    procs = running()
    if build is not None:
        return next((pid for pid, exe in procs if in_build(exe, build)), None)
    if len(procs) <= 1:
        return procs[0][0] if procs else None
    import fixinput
    want = fixinput.pipe_name().lower()
    mine = [pid for pid, exe in procs if exe and (fixinput.pipe_name_for(os.path.dirname(exe)) or '').lower() == want]
    if len(mine) == 1:
        return mine[0]
    key = tuple(sorted(pid for pid, _ in procs))
    if key not in _noted:
        _noted.add(key)
        games = '; '.join(f'{pid} {exe or "(path unreadable)"}' for pid, exe in procs)
        print(f'current_zone: {len(procs)} XMen2.exe running and {len(mine)} serve the pipe "{fixinput.pipe_name()}" '
              f'- not guessing (pass the build, or set XML2FIX_PIPE): {games}', file=sys.stderr, flush=True)
    return None


def pop_build(argv):
    """A read-only tool's `--build DIR` (taken out of argv in place) -> DIR, or None."""
    if '--build' not in argv:
        return None
    i = argv.index('--build')
    if i + 1 >= len(argv):
        sys.exit('--build needs a build folder')
    build = argv[i + 1]
    del argv[i:i + 2]
    return build


def kill_build(build, timeout=20.0):
    """End every XMen2.exe of <build> (taskkill /PID <pid> /F; never another folder's game) and wait up to
    `timeout` s until they are gone. Returns the pids it ended."""
    pids = build_pids(build)
    for pid in pids:
        subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True)
    t0 = time.time()
    while pids and build_pids(build) and time.time() - t0 < timeout:
        time.sleep(0.5)
    return pids


def read_zone(pid):
    h = k32.OpenProcess(0x0010 | 0x0400, False, pid)  # PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_string_buffer(128)
        n = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(ZONE_ADDR), buf, 128, ctypes.byref(n)):
            return None
        return buf.raw.split(b'\0')[0].decode('latin-1')
    finally:
        k32.CloseHandle(h)


if __name__ == '__main__':
    pid = game_pid(sys.argv[1] if len(sys.argv) > 1 else None)
    print(pid, read_zone(pid) if pid else None)
