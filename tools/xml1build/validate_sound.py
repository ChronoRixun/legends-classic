"""xml1build.validate_sound - ZSND bank facts and XMen2.exe sound-name resolution for validate V2/V5/V6/V8.

Reuses research/sound/zsnd.py (parser) and research/sound/simlookup.py (resolve: '\\'->'/', '<soundfile>/'
prefix for death_style*/zone_sh*, ELF hash, track table, sound table, '/***RANDOM***/0'), both importable
because xml1build.common puts research/sound on sys.path.

simlookup.load_banks() re-reads every bank on each call (x_voice.zss is 153 MB after the merge), so this
module parses each bank once, keeps (path, sound_hashes, track_hashes) tuples in the exact shape
simlookup.resolve() expects, and caches the facts in <out>/_build/validate_sound_cache.json keyed by
(size, mtime_ns) so rebuilds only re-parse banks that changed.

Engine facts used (research/_summaries/sound.md, VERIFICATION wins):
  * loader: '<bank>' -> sounds/eng/<c1>/<c2>/<bank>.zsm first (mode 1), then .zss (0x591380, path builder
    0x590a70 + 0x592b00 two-letter subdirs); zone soundfile -> <sf>_{m,a,c,v,d} (0x592050, suffixes at
    0x59228d); globals x_common + x_voice (table 0x69d064); sounddir -> '<dir>' bank (0x5923e0).
  * soundfile must be < 10 chars (0x5920cb strlen >= 10 aborts zone sounds); a soundfile ending in
    '_<a..v>' loads only that one bank (0x59210e).
  * .zsm: format 0x6a is IMA-decoded at load, anything else memcpy'd as PCM (0x595137); WAVEFORMATEX
    nBlockAlign is 2 regardless of channels (0x5950c3), so a stereo sample (flag 0x02) in a .zsm is broken.
  * .zss streams are always IMA-decoded (0x595aa0 'or [esi+0x14],1'), so a non-0x6a file in a .zss is noise.
  * bank basenames are compared on their first 9 characters for the already-loaded check (0x5913c4).
Pure except for the cache file under <out>/_build.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .lib import simlookup, zsnd       # were research/sound

IMA_FORMAT = 0x6a
STEREO_FLAG = 0x02
SUFFIXES = ('m', 'a', 'c', 'v', 'd')
GLOBAL_BANKS = ('x_common', 'x_voice')
CACHE_NAME = 'validate_sound_cache.json'
CACHE_VERSION = 2


def bank_candidates(bank):
    """norm() rels the loader tries for bank name `bank`, in order (.zsm first)."""
    b = str(bank).lower()
    if len(b) < 2:
        return []
    return [f'sounds/eng/{b[0]}/{b[1]}/{b}.zsm', f'sounds/eng/{b[0]}/{b[1]}/{b}.zss']


class BankTable:
    """Parse-once cache of every ZSND bank in <out>."""

    def __init__(self, ctx):
        self.ctx = ctx
        self._lock = threading.RLock()
        self.info = {}                      # norm rel -> fact dict
        self._cache_path = ctx.build_dir / CACHE_NAME
        self._disk = {}
        try:
            d = json.loads(self._cache_path.read_text(encoding='utf-8'))
            if d.get('version') == CACHE_VERSION:
                self._disk = d.get('banks', {})
        except (OSError, ValueError):
            self._disk = {}
        self._dirty = False

    def resolve_bank(self, bank):
        """actual out rel of the file the loader would open for bank name `bank`, or None."""
        for c in bank_candidates(bank):
            a = self.ctx.out_index.get(c)
            if a is not None:
                return a
        return None

    def facts(self, rel):
        """fact dict for one bank file (norm rel or actual rel). Keys: rel, ok, problems (hard), soft,
        platform, sounds (set), tracks (set), n_sounds, n_tracks, stereo_zsm [sample idx], zss_non_ima
        [(file idx, fmt)], formats {fmt: n}, error (exception text or None)."""
        n = rel.replace('\\', '/').lower()
        return self._facts_at(n, self.ctx.out_index.path(n))

    def facts_file(self, key, path):
        """facts of a bank outside <out> (research source, XML1 Xbox original), cached under `key`."""
        return self._facts_at(key, Path(path) if path is not None else None)

    def _facts_at(self, n, path):
        with self._lock:
            if n in self.info:
                return self.info[n]
        if path is None or not path.is_file():
            f = {'rel': n, 'ok': False, 'error': 'file not found', 'problems': [], 'soft': [], 'platform': None,
                 'sounds': set(), 'tracks': set(), 'n_sounds': 0, 'n_tracks': 0, 'stereo_zsm': [],
                 'zss_non_ima': [], 'formats': {}}
            with self._lock:
                self.info[n] = f
            return f
        st = path.stat()
        key = [st.st_size, st.st_mtime_ns]
        d = self._disk.get(n)
        if d and d.get('key') == key:
            f = dict(d)
            f['sounds'] = set(d['sounds'])
            f['tracks'] = set(d['tracks'])
        else:
            f = self._parse(n, path)
            f['key'] = key
            with self._lock:
                self._disk[n] = {**f, 'sounds': sorted(f['sounds']), 'tracks': sorted(f['tracks'])}
                self._dirty = True
        f['path'] = str(path)
        with self._lock:
            self.info[n] = f
        return f

    @staticmethod
    def _parse(n, path):
        f = {'rel': n, 'ok': False, 'error': None, 'problems': [], 'soft': [], 'platform': None,
             'sounds': set(), 'tracks': set(), 'n_sounds': 0, 'n_tracks': 0, 'stereo_zsm': [],
             'zss_non_ima': [], 'formats': {}}
        try:
            b = zsnd.load(str(path), strict=False)
        except (zsnd.ZsndError, OSError, ValueError, IndexError) as e:        # struct.error is a ValueError
            f['error'] = f'{type(e).__name__}: {e}'
            return f
        except Exception as e:   # noqa: BLE001 - any parser crash is a finding, not a validator crash
            f['error'] = f'{type(e).__name__}: {e}'
            return f
        f['platform'] = b.platform
        f['problems'] = [p for p in b.problems if not p.startswith('~')]
        f['soft'] = [p[1:] for p in b.problems if p.startswith('~')]
        f['sounds'] = {h for s in b.sounds for h in s.hashes}
        f['tracks'] = {h for t in b.tracks for h in t.hashes}
        f['n_sounds'], f['n_tracks'] = len(b.sounds), len(b.tracks)
        is_zsm = n.endswith('.zsm')
        for s in b.samples:
            if is_zsm and s.raw[2] & STEREO_FLAG:
                f['stereo_zsm'].append(s.index)
        fm = {}
        for fl in b.files:
            fmt = fl.u32(8)
            fm[fmt] = fm.get(fmt, 0) + 1
            if not is_zsm and fmt != IMA_FORMAT:
                f['zss_non_ima'].append((fl.index, fmt))
        f['formats'] = {str(k): v for k, v in fm.items()}
        f['ok'] = not f['problems'] and b.platform == 'pc'
        return f

    def lookup_tuple(self, rel):
        """(path, sound_hashes, track_hashes) - the element shape simlookup.resolve() iterates."""
        f = self.facts(rel)
        return (f.get('path') or f['rel'], f['sounds'], f['tracks'])

    def save(self):
        with self._lock:
            if not self._dirty:
                return
            live = {k: v for k, v in self._disk.items()
                    if k.startswith(EXT_PREFIX) or self.ctx.out_index.get(k) is not None}
            self.ctx.write_meta(CACHE_NAME, {'version': CACHE_VERSION, 'banks': live})
            self._dirty = False


EXT_PREFIX = '@'                  # cache keys of banks outside <out> ('@x1/...', '@src/...')


class X1Banks:
    """The ORIGINAL XML1 Xbox banks (xml1_xbox/sounds/zsds/<c1>/<c2>/<bank>.zsm|zss) as simlookup tuples, so
    validate can tell a sound name the conversion lost (resolves against XML1's own banks) from one XML1 never
    had either (inherited). XML1 loads the same bank set (x_common, x_voice, <soundfile>_{m,a,c,v,d},
    '<sounddir>' per character; research sound summary) and uses the same name hash."""

    def __init__(self, table: BankTable, root):
        self.table = table
        self.root = Path(root)
        self.by_stem = {}
        if self.root.is_dir():
            for dirpath, _, files in os.walk(self.root):
                for f in files:
                    s, e = os.path.splitext(f)
                    if e.lower() in ('.zsm', '.zss'):
                        self.by_stem.setdefault(s.lower(), []).append(Path(dirpath) / f)
        for v in self.by_stem.values():
            v.sort(key=lambda p: p.suffix.lower() != '.zsm')          # loader order: .zsm first

    def resolve_bank(self, bank):
        hits = self.by_stem.get(str(bank).lower())
        return hits[0] if hits else None

    def lookup_tuple(self, path):
        rel = Path(path).relative_to(self.root).as_posix().lower()
        f = self.table.facts_file(f'{EXT_PREFIX}x1/{rel}', path)
        return (str(path), f['sounds'], f['tracks'])

    def zone_tuples(self, soundfile, sounddirs):
        """tuples XML1 would have loaded for a zone: globals + <sf>_{m,a,c,v,d} + each character sounddir."""
        names = list(GLOBAL_BANKS)
        sf = (soundfile or '').lower()
        if len(sf) >= 2 and sf[-2] == '_' and 'a' <= sf[-1] <= 'v':
            names.append(sf)
        elif sf:
            names += [f'{sf}_{s}' for s in SUFFIXES]
        names += [d.lower() for d in sounddirs if d]
        out, seen = [], set()
        for nm in names:
            p = self.resolve_bank(nm)
            if p is not None and p not in seen:
                seen.add(p)
                out.append(self.lookup_tuple(p))
        return out


def zone_banks(table, soundfile):
    """(loaded rels, missing names) for a zone soundfile: '<sf>_x' loads only that bank (0x59210e),
    otherwise <sf>_{m,a,c,v,d}."""
    sf = (soundfile or '').lower()
    names = []
    if len(sf) >= 2 and sf[-2] == '_' and 'a' <= sf[-1] <= 'v':
        names = [sf]
    elif sf:
        names = [f'{sf}_{s}' for s in SUFFIXES]
    got, missing = [], []
    for nm in names:
        r = table.resolve_bank(nm)
        (got if r else missing).append(r or nm)
    return got, missing


def resolve(name, soundfile, bank_tuples):
    """simlookup.resolve (XMen2.exe 0x590bd0 -> 0x590e50) -> (full_name, bank_path|None, how|None)."""
    return simlookup.resolve(name, (soundfile or '').lower() or None, bank_tuples)


def names_from_tree(root):
    """Sound names in a decoded XMLB tree, with simlookup.names_from's attribute rules: attributes whose name
    contains 'sound' (or soundtoplay[b]), except soundfile/sounddir, radius/volume attributes and numbers."""
    import re
    out = []
    for el in root.iter():
        for k, v in el.attrib.items():
            kl = k.lower()
            if 'sound' not in kl or kl in ('soundfile', 'sounddir') or 'radius' in kl or 'volume' in kl:
                continue
            if not v or re.fullmatch(r'[-0-9. ]+', v):
                continue
            out.append(v.strip())
    return [n for n in out if n]


def script_sound_names(result):
    """sound("PLAY_SOUND", "<name>", ...) (XML2 sig ssas) and playBossSound("<name>", ...) literals of a
    validate_script.ScriptResult."""
    out = []
    for c in result.calls:
        if c.name == 'sound' and len(c.args) >= 2 and c.args[0].kind == 'str' and c.args[1].kind == 'str':
            if str(c.args[0].value).upper().startswith('PLAY'):
                out.append(str(c.args[1].value))
        elif c.name == 'playBossSound' and c.args and c.args[0].kind == 'str':
            out.append(str(c.args[0].value))
    return [n for n in out if n]


def sound_files(path):
    """{sound key: file index} of a bank (sound -> sample -> file), {} when it does not parse; for telling whose
    audio answers a name in a merged bank (V27 voice lines)."""
    try:
        b = zsnd.load(str(path), strict=False)
        return {h: b.samples[s.u16(0)].u16(0) for s in b.sounds for h in s.hashes}
    except Exception:   # noqa: BLE001 - V8 reports unparsable banks
        return {}


def file_count(path):
    try:
        return len(zsnd.load(str(path), strict=False).files)
    except Exception:   # noqa: BLE001
        return 0


def answer_file(files, name):
    """file index of the sound that answers `name` (the name itself, else random variant 0), or None."""
    from .lib.zhash import elf_hash
    h = elf_hash(name.replace('\\', '/'))
    if h not in files:
        h = elf_hash('/***RANDOM***/0', h)
    return files.get(h)


def file_size_ok(path):
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def is_under(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False
