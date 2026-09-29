"""Capture OutputDebugString output from all processes (DBWIN protocol) to a file.

usage: python dbwin.py <out.log> [process-name-filter-pid]
"""
import ctypes, ctypes.wintypes as w, sys, time

k32 = ctypes.windll.kernel32
k32.CreateEventW.restype = w.HANDLE
k32.CreateFileMappingW.restype = w.HANDLE
k32.MapViewOfFile.restype = ctypes.c_void_p
k32.MapViewOfFile.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.DWORD, ctypes.c_size_t]

buffer_ready = k32.CreateEventW(None, False, False, 'DBWIN_BUFFER_READY')
data_ready = k32.CreateEventW(None, False, False, 'DBWIN_DATA_READY')
mapping = k32.CreateFileMappingW(w.HANDLE(-1), None, 4, 0, 4096, 'DBWIN_BUFFER')
view = k32.MapViewOfFile(mapping, 4, 0, 0, 4096)
if not (buffer_ready and data_ready and mapping and view):
    raise SystemExit('could not open DBWIN objects (is another debug-output viewer running?)')

out = open(sys.argv[1], 'a', encoding='latin-1', buffering=1)
only_pid = int(sys.argv[2]) if len(sys.argv) > 2 else None
while True:
    k32.SetEvent(buffer_ready)
    if k32.WaitForSingleObject(data_ready, 1000) != 0:
        continue
    pid = ctypes.c_uint32.from_address(view).value
    text = ctypes.string_at(view + 4).decode('latin-1')
    if only_pid is None or pid == only_pid:
        out.write(f'{time.strftime("%H:%M:%S")} {pid} {text.rstrip()}\n')
