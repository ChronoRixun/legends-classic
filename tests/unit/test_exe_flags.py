"""E12 (SPEC 108): xml1build.exe_flags sets the large-address-aware flag on the build's own XMen2.exe copy - one word
of the PE file header, the checksum kept valid when the exe has one - and V1 accepts exactly that difference.
Synthetic PE headers only; no game data."""
import struct
from pathlib import Path
from types import SimpleNamespace

from xml1build import exe_flags as EF


def retail_layout(checksum=0, characteristics=0x10F, size=0x400):
    """a PE32 header laid out as the retail XMen2.exe's (e_lfanew 0x130), with made-up content after it."""
    b = bytearray(size)
    b[0:2] = b'MZ'
    struct.pack_into('<I', b, 0x3C, 0x130)
    b[0x130:0x134] = b'PE\0\0'
    struct.pack_into('<H', b, 0x134, 0x14C)
    struct.pack_into('<H', b, 0x146, characteristics)
    struct.pack_into('<H', b, 0x148, 0x10B)
    struct.pack_into('<I', b, 0x164, 0x400000)
    struct.pack_into('<I', b, 0x188, checksum)
    for i in range(0x300, size):
        b[i] = (i * 7) & 0xFF
    return bytes(b)


def test_retail_word_and_nothing_else():
    src = retail_layout()
    out = EF.with_laa(src)
    assert EF.laa_state(src) == 'off' and EF.laa_state(out) == 'on'
    assert struct.unpack_from('<H', out, EF.RETAIL_OFFSET)[0] == 0x012F
    assert EF.differences(src, out) == [0x146] and len(out) == len(src)
    h = EF.header(src)
    assert h['characteristics_at'] == EF.RETAIL_OFFSET and h['characteristics'] == EF.RETAIL_CHARACTERISTICS
    assert EF.with_laa(out) == out                              # already set: unchanged


def test_nonzero_checksum_recomputed():
    src = retail_layout()
    at = EF.header(src)['checksum_at']
    signed = bytearray(src)
    struct.pack_into('<I', signed, at, EF.pe_checksum(src, at))
    signed = bytes(signed)
    out = EF.with_laa(signed)
    assert EF.differences(signed, out)[0] == 0x146 and set(EF.differences(signed, out)) <= {0x146, at, at + 1, at + 2,
                                                                                         at + 3}
    assert struct.unpack_from('<I', out, at)[0] == EF.pe_checksum(out, at) != struct.unpack_from('<I', signed, at)[0]
    try:
        import pefile
    except ImportError:
        return
    pe = pefile.PE(data=out, fast_load=True)
    assert pe.generate_checksum() == struct.unpack_from('<I', out, at)[0]


def test_zero_checksum_stays_zero():
    out = EF.with_laa(retail_layout())
    assert struct.unpack_from('<I', out, 0x188)[0] == 0


def test_not_pe32_refused():
    for data in (b'', b'MZ' + b'\0' * 0x3E, retail_layout()[:0x140]):
        try:
            EF.header(data)
        except EF.NotPE32:
            continue
        raise AssertionError(f'{data[:4]!r}: accepted')
    pe64 = bytearray(retail_layout())
    struct.pack_into('<H', pe64, 0x148, 0x20B)
    try:
        EF.with_laa(bytes(pe64))
    except EF.NotPE32:
        pass
    else:
        raise AssertionError('PE32+ accepted')


def test_validate_accepts_only_the_flag():
    src = retail_layout()
    out = EF.with_laa(src)
    assert EF.validate(out, src, 'on') == [] and EF.validate(src, src, 'off') == []
    assert EF.validate(src, src, 'on') and EF.validate(out, src, 'off')       # the wrong state either way
    other = bytearray(out)
    other[0x350] ^= 1
    errs = EF.validate(bytes(other), src, 'on')
    assert errs and '0x350' in errs[0]
    assert 'size' in EF.validate(out + b'x', src, 'on')[0]


class _Ctx:
    def __init__(self, base: Path, laa):
        self.args = SimpleNamespace(laa=laa)
        self.base_index = SimpleNamespace(path=lambda rel: base / rel if (base / rel).is_file() else None)
        self.written, self.notes, self.errors = {}, [], []

    def opt(self, name, default=None):
        return getattr(self.args, name, default)

    def write_bytes(self, rel, data, *, source=None, **_):
        self.written[rel] = (data, source)

    def note(self, msg):
        self.notes.append(msg)

    def error(self, msg):
        self.errors.append(msg)


def test_run_writes_the_copy_never_the_source():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        src = retail_layout()
        (base / 'XMen2.exe').write_bytes(src)
        ctx = _Ctx(base, 'on')
        EF.run(ctx)
        data, source = ctx.written['XMen2.exe']
        assert data == EF.with_laa(src) and Path(source) == base / 'XMen2.exe' and not ctx.errors
        assert (base / 'XMen2.exe').read_bytes() == src
        assert '0x146' in ctx.notes[0] and '0x010f -> 0x012f' in ctx.notes[0]
        off = _Ctx(base, 'off')
        EF.run(off)
        assert not off.written and not off.errors and 'byte-identical' in off.notes[0]
        (base / 'XMen2.exe').write_bytes(b'not a program')
        bad = _Ctx(base, 'on')
        EF.run(bad)
        assert not bad.written and bad.errors


def test_build_option_and_content_opt():
    import build_xml1
    assert build_xml1.parse_args(['--out', '.']).laa == 'on'
    assert build_xml1.parse_args(['--out', '.', '--laa', 'off']).laa == 'off'
    assert build_xml1.CONTENT_OPTS['laa'] == ('exe_flags', 'on') and build_xml1.LEGACY_OPT_VALUES['laa'] == 'off'
    from xml1build import common as C
    assert C.MODULE_ORDER.index('exe_flags') < C.MODULE_ORDER.index('savefiles') == len(C.MODULE_ORDER) - 1
    from xml1builder import cli
    p = cli.make_parser()
    assert p.parse_args(['build']).laa == 'on' and p.parse_args(['build', '--no-laa']).laa == 'off'
