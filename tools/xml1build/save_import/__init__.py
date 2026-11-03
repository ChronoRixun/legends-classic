"""Offline XML1 campaign import core. No retail checkpoint is admitted yet.

Only confirmed wire fields are decoded automatically. Semantic interpretations
come from an explicit, build-bound table; approximations require opt-in.
"""

from .errors import ImportRefusal

__all__ = ['ImportRefusal']
