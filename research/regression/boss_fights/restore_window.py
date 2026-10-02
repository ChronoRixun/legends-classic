"""Restore the game's window without stealing focus (ShowWindow SW_SHOWNOACTIVATE): a minimised game draws no frames."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import ctypes, ctypes.wintypes as w, sys
sys.path.insert(0, _REPO + '/tools')
import current_zone as CZ
u = ctypes.windll.user32
pid = CZ.game_pid(sys.argv[1] if len(sys.argv) > 1 else _REPO + '/build/_t16')
found = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
def cb(h, _):
    p = w.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(p))
    if p.value == pid and u.IsWindowVisible(h) or (p.value == pid and u.IsIconic(h)):
        found.append(h)
    return True
u.EnumWindows(cb, 0)
for h in found:
    title = ctypes.create_unicode_buffer(256); u.GetWindowTextW(h, title, 256)
    print(hex(h), repr(title.value), 'iconic', bool(u.IsIconic(h)))
    if u.IsIconic(h):
        u.ShowWindow(h, 4)  # SW_SHOWNOACTIVATE
        print('restored')
