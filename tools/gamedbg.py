"""Minimal Win32 debugger: launch a (32-bit) game, log debug strings, exceptions and exit code.

usage: gamedbg.py <log> <exe> [args...]
"""
import ctypes, ctypes.wintypes as w, os, sys, time

k32 = ctypes.WinDLL('kernel32', use_last_error=True)

DEBUG_ONLY_THIS_PROCESS = 0x2
DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001
EXCEPTION_DEBUG_EVENT, CREATE_THREAD, CREATE_PROCESS, EXIT_THREAD, EXIT_PROCESS, LOAD_DLL, UNLOAD_DLL, OUTPUT_DEBUG_STRING, RIP = range(1, 10)
BENIGN = {0x80000003, 0x4000001F, 0x406D1388, 0x40010006, 0x4001000A}  # breakpoints, thread naming, DBG_PRINTEXCEPTION


class STARTUPINFO(ctypes.Structure):
    _fields_ = [('cb', w.DWORD), ('lpReserved', w.LPWSTR), ('lpDesktop', w.LPWSTR), ('lpTitle', w.LPWSTR),
                ('dwX', w.DWORD), ('dwY', w.DWORD), ('dwXSize', w.DWORD), ('dwYSize', w.DWORD),
                ('dwXCountChars', w.DWORD), ('dwYCountChars', w.DWORD), ('dwFillAttribute', w.DWORD),
                ('dwFlags', w.DWORD), ('wShowWindow', w.WORD), ('cbReserved2', w.WORD),
                ('lpReserved2', ctypes.c_void_p), ('hStdInput', w.HANDLE), ('hStdOutput', w.HANDLE),
                ('hStdError', w.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [('hProcess', w.HANDLE), ('hThread', w.HANDLE), ('dwProcessId', w.DWORD), ('dwThreadId', w.DWORD)]


class EXCEPTION_RECORD(ctypes.Structure):
    pass


EXCEPTION_RECORD._fields_ = [('ExceptionCode', w.DWORD), ('ExceptionFlags', w.DWORD),
                             ('ExceptionRecord', ctypes.c_void_p), ('ExceptionAddress', ctypes.c_void_p),
                             ('NumberParameters', w.DWORD), ('ExceptionInformation', ctypes.c_size_t * 15)]


class EXCEPTION_DEBUG_INFO(ctypes.Structure):
    _fields_ = [('ExceptionRecord', EXCEPTION_RECORD), ('dwFirstChance', w.DWORD)]


class LOAD_DLL_DEBUG_INFO(ctypes.Structure):
    _fields_ = [('hFile', w.HANDLE), ('lpBaseOfDll', ctypes.c_void_p), ('dwDebugInfoFileOffset', w.DWORD),
                ('nDebugInfoSize', w.DWORD), ('lpImageName', ctypes.c_void_p), ('fUnicode', w.WORD)]


class CREATE_PROCESS_DEBUG_INFO(ctypes.Structure):
    _fields_ = [('hFile', w.HANDLE), ('hProcess', w.HANDLE), ('hThread', w.HANDLE),
                ('lpBaseOfImage', ctypes.c_void_p), ('dwDebugInfoFileOffset', w.DWORD),
                ('nDebugInfoSize', w.DWORD), ('lpThreadLocalBase', ctypes.c_void_p),
                ('lpStartAddress', ctypes.c_void_p), ('lpImageName', ctypes.c_void_p), ('fUnicode', w.WORD)]


class OUTPUT_DEBUG_STRING_INFO(ctypes.Structure):
    _fields_ = [('lpDebugStringData', ctypes.c_void_p), ('fUnicode', w.WORD), ('nDebugStringLength', w.WORD)]


class EXIT_PROCESS_DEBUG_INFO(ctypes.Structure):
    _fields_ = [('dwExitCode', w.DWORD)]


class _U(ctypes.Union):
    _fields_ = [('Exception', EXCEPTION_DEBUG_INFO), ('CreateProcessInfo', CREATE_PROCESS_DEBUG_INFO),
                ('LoadDll', LOAD_DLL_DEBUG_INFO), ('DebugString', OUTPUT_DEBUG_STRING_INFO),
                ('ExitProcess', EXIT_PROCESS_DEBUG_INFO), ('pad', ctypes.c_byte * 160)]


class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [('dwDebugEventCode', w.DWORD), ('dwProcessId', w.DWORD), ('dwThreadId', w.DWORD), ('u', _U)]


class WOW64_CONTEXT(ctypes.Structure):
    _fields_ = [('ContextFlags', w.DWORD), ('Dr', w.DWORD * 6), ('FloatSave', ctypes.c_byte * 112),
                ('SegGs', w.DWORD), ('SegFs', w.DWORD), ('SegEs', w.DWORD), ('SegDs', w.DWORD),
                ('Edi', w.DWORD), ('Esi', w.DWORD), ('Ebx', w.DWORD), ('Edx', w.DWORD), ('Ecx', w.DWORD),
                ('Eax', w.DWORD), ('Ebp', w.DWORD), ('Eip', w.DWORD), ('SegCs', w.DWORD), ('EFlags', w.DWORD),
                ('Esp', w.DWORD), ('SegSs', w.DWORD), ('ExtendedRegisters', ctypes.c_byte * 512)]


k32.OpenThread.restype = w.HANDLE
k32.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]


def read_mem(hproc, addr, size):
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t()
    if not k32.ReadProcessMemory(hproc, ctypes.c_void_p(addr), buf, size, ctypes.byref(n)):
        return b''
    return buf.raw[:n.value]


def file_name(h):
    buf = ctypes.create_unicode_buffer(520)
    if h and k32.GetFinalPathNameByHandleW(h, buf, 520, 0):
        return os.path.basename(buf.value)
    return '?'


def main(log_path, exe, *args):
    log = open(log_path, 'w', encoding='latin-1', buffering=1)
    say = lambda s: log.write(f'{time.strftime("%H:%M:%S")} {s}\n')
    si = STARTUPINFO(cb=ctypes.sizeof(STARTUPINFO))
    pi = PROCESS_INFORMATION()
    cmd = ' '.join(f'"{a}"' for a in (exe,) + args)
    if not k32.CreateProcessW(None, cmd, None, None, False, DEBUG_ONLY_THIS_PROCESS, None,
                              os.path.dirname(exe), ctypes.byref(si), ctypes.byref(pi)):
        raise SystemExit(f'CreateProcess failed: {ctypes.get_last_error()}')
    say(f'started pid {pi.dwProcessId}')
    modules = {}
    sizes = {}

    def add_module(base, name):
        modules[base] = name
        hdr = read_mem(pi.hProcess, base, 0x400)
        if len(hdr) >= 0x100:
            pe = int.from_bytes(hdr[0x3C:0x40], 'little')
            sizes[base] = int.from_bytes(read_mem(pi.hProcess, base + pe + 0x50, 4) or b'\0' * 4, 'little')

    def in_module(addr):
        return any(b <= addr < b + sizes.get(b, 0) for b in modules)

    def dump_state(tid):
        th = k32.OpenThread(0x1FFFFF, False, tid)
        ctx = WOW64_CONTEXT(ContextFlags=0x10007)
        if not th or not k32.Wow64GetThreadContext(th, ctypes.byref(ctx)):
            say('  (no thread context)')
            return
        regs = ' '.join(f'{r}={getattr(ctx, r):08x}' for r in ('Eax', 'Ebx', 'Ecx', 'Edx', 'Esi', 'Edi', 'Ebp', 'Esp', 'Eip'))
        say('  ' + regs)
        stack = read_mem(pi.hProcess, ctx.Esp, 0x800)
        frames = 0
        for i in range(0, len(stack) - 3, 4):
            v = int.from_bytes(stack[i:i + 4], 'little')
            if in_module(v):
                say(f'  [esp+{i:#05x}] {where(v)}')
                frames += 1
                if frames >= 24:
                    break
        for r in ('Eax', 'Ebx', 'Ecx', 'Edx', 'Esi', 'Edi'):
            v = getattr(ctx, r)
            txt = read_mem(pi.hProcess, v, 64).split(b'\0')[0] if v > 0x10000 else b''
            if txt and all(32 <= c < 127 for c in txt) and len(txt) >= 3:
                say(f'  {r} -> "{txt.decode()}"')

    def where(addr):
        best = max((b for b in modules if b <= addr), default=None)
        return f'{modules[best]}+{addr - best:#x}' if best is not None else hex(addr)

    ev = DEBUG_EVENT()
    while True:
        if not k32.WaitForDebugEvent(ctypes.byref(ev), 0xFFFFFFFF):
            break
        status = DBG_CONTINUE
        code = ev.dwDebugEventCode
        if code == CREATE_PROCESS:
            info = ev.u.CreateProcessInfo
            add_module(info.lpBaseOfImage, file_name(info.hFile))
        elif code == LOAD_DLL:
            info = ev.u.LoadDll
            add_module(info.lpBaseOfDll, file_name(info.hFile))
        elif code == OUTPUT_DEBUG_STRING:
            info = ev.u.DebugString
            raw = read_mem(pi.hProcess, info.lpDebugStringData,
                           info.nDebugStringLength * (2 if info.fUnicode else 1))
            text = raw.decode('utf-16-le' if info.fUnicode else 'latin-1', 'replace').rstrip('\0').rstrip()
            say(f'DBG {text}')
        elif code == EXCEPTION_DEBUG_EVENT:
            rec = ev.u.Exception.ExceptionRecord
            first = ev.u.Exception.dwFirstChance
            if rec.ExceptionCode not in BENIGN:
                params = [hex(rec.ExceptionInformation[i]) for i in range(rec.NumberParameters)]
                say(f'EXCEPTION {rec.ExceptionCode:#010x} {"first" if first else "SECOND"}-chance at '
                    f'{where(rec.ExceptionAddress or 0)} params={params}')
                if first:
                    dump_state(ev.dwThreadId)
                status = DBG_EXCEPTION_NOT_HANDLED
        elif code == EXIT_PROCESS:
            say(f'EXIT code {ev.u.ExitProcess.dwExitCode:#x}')
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
            break
        k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)


if __name__ == '__main__':
    main(*sys.argv[1:])
