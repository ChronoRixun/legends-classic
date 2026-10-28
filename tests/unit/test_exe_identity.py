"""The retail XMen2.exe is recognised by a normalized fingerprint (data/known_xml2.json): the large-address-aware
flag and the PE checksum may differ, nothing else. Synthetic PE images stand in for the exe (no game data); the
last test also runs against a real retail exe when one is present (LC_RETAIL_XMEN2, else the usual install folder)
and is skipped otherwise."""
import hashlib
import os
import struct
import tempfile
import unittest
from pathlib import Path

import builder_stub as B
from test_exe_flags import retail_layout
from xml1build import exe_flags as EF
from xml1builder import inputs as I
from xml1builder.errors import BuilderError

SIZE = 0x1000


def stand_in(**kw):
    return retail_layout(size=SIZE, **kw)


def entries(retail):
    return {hashlib.md5(retail).hexdigest(): {'id': 'retail-en', 'size': len(retail),
                                               'normalized_sha256': EF.normalized_sha256(retail)}}


class Known:
    """known_exes() replaced by the stand-in retail exe's entry."""

    def __init__(self, retail):
        self.table = entries(retail)

    def __enter__(self):
        self.old = I.known_exes
        I.known_exes = lambda: self.table

    def __exit__(self, *a):
        I.known_exes = self.old


def with_checksum(data, value):
    out = bytearray(data)
    struct.pack_into('<I', out, EF.header(data)['checksum_at'], value)
    return bytes(out)


def refused(folder):
    try:
        I.check_xml2(folder)
    except BuilderError as e:
        assert e.code == 'E_XML2_UNKNOWN_EXE' and e.exit_code == 3 and e.detail['exe_md5'], (e.code, e.detail)
        return e
    raise AssertionError('accepted')


def test_normalization_touches_only_the_two_fields():
    retail = stand_in()
    flagged = EF.with_laa(retail)
    assert flagged != retail and EF.normalized(flagged) == retail == EF.normalized(retail)
    odd = with_checksum(flagged, 0xDEADBEEF)
    assert EF.normalized(odd) == retail and EF.normalized_sha256(odd) == EF.normalized_sha256(retail)
    changed = bytearray(retail)
    changed[0x3F0] ^= 1
    assert EF.normalized_sha256(bytes(changed)) != EF.normalized_sha256(retail)
    stamp = bytearray(retail)                                # the link timestamp is not one of the two fields
    stamp[0x130 + 8] ^= 1
    assert EF.normalized_sha256(bytes(stamp)) != EF.normalized_sha256(retail)


def test_identify_exe_cases():
    retail = stand_in()
    with Known(retail):
        assert I.identify_exe(retail)[1] == I.EXE_RETAIL
        for data in (EF.with_laa(retail), with_checksum(retail, 0x1234), with_checksum(EF.with_laa(retail), 7)):
            entry, found = I.identify_exe(data)
            assert entry['id'] == 'retail-en' and found == I.EXE_RETAIL_PATCHED == 'retail (header-patched: LAA/checksum)'
        code = bytearray(EF.with_laa(retail))
        code[0x500] ^= 0xFF
        assert I.identify_exe(bytes(code)) == (None, I.EXE_CODE_DIFFERS)
        assert I.EXE_CODE_DIFFERS == 'modified XMen2.exe (code differs from retail)'
        assert I.identify_exe(retail[:-1]) == (None, I.EXE_OTHER_BUILD)
        assert I.identify_exe(retail + b'\0') == (None, I.EXE_OTHER_BUILD)
        assert I.EXE_OTHER_BUILD == 'different XMen2.exe build'
        # same size, not a 32-bit x86 PE at all: not retail either
        assert I.identify_exe(b'M' * SIZE) == (None, I.EXE_CODE_DIFFERS)


def test_check_xml2_accepts_header_patches_refuses_everything_else():
    retail = stand_in()
    with tempfile.TemporaryDirectory() as td, Known(retail):
        xml2 = B.make_xml2(Path(td) / 'xml2')
        exe = xml2 / 'XMen2.exe'
        for name, data in (('retail', retail), ('laa', EF.with_laa(retail)), ('checksum', with_checksum(retail, 99)),
                           ('both', with_checksum(EF.with_laa(retail), 12345))):
            exe.write_bytes(data)
            info = I.check_xml2(xml2)
            assert info['exe_known'] and info['exe'] == 'retail-en', name
            assert info['exe_md5'] == hashlib.md5(data).hexdigest(), name
            assert info['exe_found'] == (I.EXE_RETAIL if data == retail else I.EXE_RETAIL_PATCHED), name
        code = bytearray(EF.with_laa(retail))
        code[0x777] ^= 0x01
        exe.write_bytes(bytes(code))
        e = refused(xml2)
        assert e.detail['found'] == I.EXE_CODE_DIFFERS and I.EXE_CODE_DIFFERS in e.msg, e.msg
        exe.write_bytes(retail[:SIZE // 2])
        e = refused(xml2)                                     # truncated
        assert e.detail['found'] == I.EXE_OTHER_BUILD and I.EXE_OTHER_BUILD in e.msg, e.msg
        exe.write_bytes(retail + b'extra')
        assert refused(xml2).detail['found'] == I.EXE_OTHER_BUILD
        # --allow-unknown-exe still lets a refused one through, with the same reason in the warning
        exe.write_bytes(bytes(code))
        warned = []
        info = I.check_xml2(xml2, allow_unknown=True, warn=lambda c, m, d: warned.append((c, m)))
        assert not info['exe_known'] and warned[0][0] == 'W_XML2_UNKNOWN_EXE' and I.EXE_CODE_DIFFERS in warned[0][1]
        # an accepted header-patched exe raises no warning
        exe.write_bytes(EF.with_laa(retail))
        warned.clear()
        I.check_xml2(xml2, allow_unknown=True, warn=lambda *a: warned.append(a))
        assert not warned


class _Ctx:
    def __init__(self, base):
        self.written, self.notes, self.errors = {}, [], []
        self.base_index = type('Idx', (), {'path': lambda s, rel: base / rel})()

    def opt(self, name, default=None):
        return 'on'

    def write_bytes(self, rel, data, source=None):
        self.written[rel] = (data, source)

    def note(self, msg):
        self.notes.append(msg)

    def error(self, msg):
        self.errors.append(msg)


def test_build_copy_step_with_an_already_flagged_source():
    retail = stand_in()
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        for src in (EF.with_laa(retail), with_checksum(EF.with_laa(retail), 0xCAFE), with_checksum(retail, 0xCAFE)):
            (base / 'XMen2.exe').write_bytes(src)
            ctx = _Ctx(base)
            EF.run(ctx)
            assert not ctx.errors
            if EF.laa_state(src) == 'on':                    # already flagged: copied unchanged, not flipped back
                assert not ctx.written and 'already large-address-aware' in ctx.notes[0]
            else:                                            # the checksum was rewritten: the new one stays valid
                out = ctx.written['XMen2.exe'][0]
                assert EF.laa_state(out) == 'on'
                assert EF.header(out)['checksum'] == EF.pe_checksum(out, EF.header(out)['checksum_at'])
            assert EF.expected(src, 'on') == (src if EF.laa_state(src) == 'on' else EF.with_laa(src))


def _real_retail():
    for c in (os.environ.get('LC_RETAIL_XMEN2', ''), 'D:/Games/X-Men Legends II/XMen2.exe'):
        if c and Path(c).is_file():
            d = Path(c).read_bytes()
            if hashlib.md5(d).hexdigest() in I.known_exes():
                return d
    return None


def test_real_retail_exe_if_present():
    real = _real_retail()
    if real is None:
        raise unittest.SkipTest('no retail XMen2.exe at hand (set LC_RETAIL_XMEN2)')
    assert I.identify_exe(real)[1] == I.EXE_RETAIL
    flagged = EF.with_laa(real)
    assert flagged != real and EF.header(flagged)['characteristics_at'] == 0x146
    entry = I.known_exes()[hashlib.md5(real).hexdigest()]
    for data in (flagged, with_checksum(real, 0x00C0FFEE), with_checksum(flagged, 1)):
        assert I.identify_exe(data) == (entry, I.EXE_RETAIL_PATCHED)
    code = bytearray(flagged)
    code[0x1000] ^= 1
    assert I.identify_exe(bytes(code)) == (None, I.EXE_CODE_DIFFERS)
    assert I.identify_exe(real[:-100]) == (None, I.EXE_OTHER_BUILD)
    assert entry['normalized_sha256'] == EF.normalized_sha256(real)
