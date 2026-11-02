"""xml1build.exe_flags - the build's own XMen2.exe runs large-address-aware (PLAN row E12; SPEC 108).

XMen2.exe is a 32-bit program without the IMAGE_FILE_LARGE_ADDRESS_AWARE flag, so Windows gives it 2 GB of address
space. With the flag a 32-bit process on 64-bit Windows (and under Wine / Proton) gets 4 GB, which the raised engine
limits and bigger assets need. Windows reads the flag from the exe's file header when the process starts, so there is
no runtime switch: the build sets it on its own copy of the exe (one word of the PE file header; for the retail exe
file offset 0x146, 0x010f -> 0x012f). The retail exe has no PE checksum (0), so nothing else changes; an exe with a
nonzero checksum gets it recomputed. The source install's exe is never written (ctx.write_bytes replaces <out>'s file
atomically; _check_out_safe keeps <out> away from the install).

--laa off (A/B builds) leaves the base sync's byte-identical copy of the install's exe in <out>.
XML2 Fix logs the state at start ("limits: address space - LAA on|off ...") and the test pipe's status shows it."""
from __future__ import annotations

import hashlib
import struct

MODULE = 'exe_flags'
EXE = 'XMen2.exe'
LAA = 0x0020                       # IMAGE_FILE_LARGE_ADDRESS_AWARE
MODES = ('on', 'off')
DEFAULT = 'on'
RETAIL_CHARACTERISTICS = 0x010F    # relocs stripped, executable, line numbers / local symbols stripped
RETAIL_OFFSET = 0x146              # e_lfanew 0x130 + 4 + 0x12


class NotPE32(ValueError):
    pass


def header(data: bytes) -> dict:
    """{'characteristics_at', 'characteristics', 'checksum_at', 'checksum'} of a 32-bit x86 PE image, or NotPE32."""
    if len(data) < 0x40 or data[:2] != b'MZ':
        raise NotPE32('no MZ header')
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    if pe + 0x18 + 0x44 > len(data) or data[pe:pe + 4] != b'PE\0\0':
        raise NotPE32('no PE header')
    machine = struct.unpack_from('<H', data, pe + 4)[0]
    magic = struct.unpack_from('<H', data, pe + 0x18)[0]
    if machine != 0x14C or magic != 0x10B:
        raise NotPE32(f'not a 32-bit x86 image (machine {machine:#x}, optional header {magic:#x})')
    at = pe + 0x16
    return {'characteristics_at': at, 'characteristics': struct.unpack_from('<H', data, at)[0],
            'checksum_at': pe + 0x58, 'checksum': struct.unpack_from('<I', data, pe + 0x58)[0]}


def pe_checksum(data: bytes, checksum_at: int) -> int:
    """the PE image checksum (CheckSumMappedFile's algorithm): 16-bit one's-complement-style sum of the file with the
    checksum field taken as 0, folded to 16 bits, plus the file length."""
    buf = bytearray(data)
    buf[checksum_at:checksum_at + 4] = b'\0\0\0\0'
    if len(buf) % 2:
        buf.append(0)
    total = 0
    for (word,) in struct.iter_unpack('<H', bytes(buf)):
        total += word
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + len(data)) & 0xFFFFFFFF


def normalized(data: bytes) -> bytes:
    """data with exactly the two harmless header fields normalized: the LAA bit cleared in the COFF characteristics
    and the optional-header CheckSum zeroed (both located through the PE header). A 4 GB patcher and a rewritten
    PE checksum are the only edits that leave a retail exe's identity unchanged; NotPE32 for anything else."""
    h = header(data)
    out = bytearray(data)
    struct.pack_into('<H', out, h['characteristics_at'], h['characteristics'] & ~LAA & 0xFFFF)
    struct.pack_into('<I', out, h['checksum_at'], 0)
    return bytes(out)


def normalized_sha256(data: bytes) -> str:
    """sha256 of normalized(data): the retail exe's identity independent of the LAA flag and the PE checksum."""
    return hashlib.sha256(normalized(data)).hexdigest()


def laa_state(data: bytes) -> str:
    """'on' / 'off' (the flag in the file header)."""
    return 'on' if header(data)['characteristics'] & LAA else 'off'


def with_laa(data: bytes) -> bytes:
    """data with the LAA flag set (and its PE checksum recomputed if it has one). Already set: data unchanged."""
    h = header(data)
    if h['characteristics'] & LAA:
        return data
    out = bytearray(data)
    struct.pack_into('<H', out, h['characteristics_at'], h['characteristics'] | LAA)
    if h['checksum']:
        struct.pack_into('<I', out, h['checksum_at'], pe_checksum(bytes(out), h['checksum_at']))
    return bytes(out)


def differences(base: bytes, built: bytes) -> list:
    """byte offsets where built differs from base (the same length assumed by the caller)."""
    return [i for i in range(min(len(base), len(built))) if base[i] != built[i]]


def expected(base: bytes, mode: str) -> bytes:
    return with_laa(base) if mode == 'on' else base


def mode(ctx) -> str:
    m = (ctx.opt('laa', DEFAULT) or DEFAULT).lower()
    return m if m in MODES else DEFAULT


def run(ctx):
    src = ctx.base_index.path(EXE)
    if src is None:
        ctx.error(f'the XML2 install has no {EXE}')
        return
    want = mode(ctx)
    data = src.read_bytes()
    try:
        h = header(data)
    except NotPE32 as e:
        ctx.error(f'{EXE}: {e}; the large-address-aware flag cannot be set')
        return
    if want == 'off':
        ctx.note(f'--laa off: {EXE} stays the install\'s byte-identical copy (2 GB address space)')
        return
    if h['characteristics'] & LAA:
        ctx.note(f'{EXE} of the install is already large-address-aware: copied unchanged')
        return
    patched = with_laa(data)
    ctx.write_bytes(EXE, patched, source=str(src))
    where = h['characteristics_at']
    ctx.note(f'{EXE}: large-address-aware set on the build\'s copy (file offset {where:#x}: '
             f'{h["characteristics"]:#06x} -> {h["characteristics"] | LAA:#06x}; PE checksum '
             f'{"recomputed" if h["checksum"] else "0, unchanged"})')
    if where != RETAIL_OFFSET or h['characteristics'] != RETAIL_CHARACTERISTICS:
        ctx.note(f'{EXE} is not the retail header layout ({where:#x} / {h["characteristics"]:#06x}); the flag was set '
                 'on its own header')


def validate(out_exe: bytes, base_exe: bytes, want: str) -> list:
    """V1 (E12): the build's exe is the install's exe, plus the LAA flag (and checksum) with --laa on.
    -> error strings."""
    if len(out_exe) != len(base_exe):
        return [f'{EXE} differs in size from the base install (the build only sets the large-address-aware flag)']
    try:
        exp = expected(base_exe, want)
    except NotPE32 as e:
        return [f'{EXE} of the base install: {e}'] if want == 'on' and out_exe != base_exe else []
    if out_exe == exp:
        return []
    diff = differences(exp, out_exe)
    what = "the install's exe with the large-address-aware flag" if want == 'on' else "the install's exe"
    return [f'{EXE} differs from {what} at {len(diff)} byte(s) (first file offset {diff[0]:#x}; --laa {want})']
