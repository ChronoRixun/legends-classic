"""Release keys must refuse a companion missing any one new capability."""
import tempfile
from pathlib import Path
from xml1build import fix_ini as F


def test_023c_release_capabilities_refuse_individually():
    keys = {section: {name: '1' for name in names} for section, names in F.RELEASE_16_KEYS.items()}
    for absent in ('DangerRoomParty', 'Xml1LockOnEffects', 'Xml1LockOnAim'):
        with tempfile.TemporaryDirectory() as temp:
            dll = Path(temp) / 'invented.dll'
            dll.write_bytes(b'MZ' + b''.join(name.encode('utf-16le') + b'\0\0'
                                           for section in keys.values() for name in section if name != absent))
            try:
                F.check_release_dll(dll, keys)
            except F.FixTooOld as exc:
                assert exc.missing == ['[Game] ' + absent]
            else:
                raise AssertionError('missing release capability was accepted')
            assert F.old_fix_keys(dll, keys) == ['[Game] ' + absent]
            dll.write_bytes(dll.read_bytes() + absent.encode('utf-16le'))
            F.check_release_dll(dll, keys)
