"""Read-only companion capability checks; never load or execute the player's DLL.

As with the builder's other DLL gates, exact terminated capability strings are
an interoperability check, not authentication or proof of runtime acceptance.
"""
from __future__ import annotations

from .errors import ImportRefusal
from .source import bounded_read, digest, safe_path
from .writer_lock import LOCK_NAME, PROTOCOL

MAX_DLL = 64 << 20


def _literal(data, value):
    return any((value + '\0').encode(encoding) in data for encoding in ('ascii', 'utf-16le'))


class Companion:
    def __init__(self, build):
        self.build = safe_path(build, directory=True)
        self.path = safe_path(self.build / 'dinput.dll')
        self.report = self._inspect()

    def _inspect(self):
        if not self.path.exists():
            return dict(sha256=None, protocol=None)
        data = bounded_read(self.path, MAX_DLL)
        supported = data.startswith(b'MZ') and _literal(data, PROTOCOL) and _literal(data, LOCK_NAME)
        return dict(sha256=digest(data), protocol=PROTOCOL if supported else None)

    def require(self):
        if self.report['protocol'] != PROTOCOL:
            raise ImportRefusal('DLL', 'The installed dinput.dll must advertise the SaveLC writer lease.',
                                required_protocol=PROTOCOL, companion=self.report)

    def recheck(self):
        if self._inspect() != self.report:
            raise ImportRefusal('CHANGED', 'The companion DLL changed. Close the game and preview again.')
