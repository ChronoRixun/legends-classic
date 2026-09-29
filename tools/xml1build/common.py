"""xml1build.common - the shared build context (ctx) for tools/build_xml1.py.

Every module (characters, scripts, zones, media, testhooks, validate) receives ONE BuildContext and must
read inputs and write outputs only through it (see tools/xml1build/SPEC.md, section 3). The context gives:

  * paths (out, base, XML1 sources, research) from a Sources object (xml1build/sources.py: developer mode = the
    repo's folders below, prepared mode = the prepare stages' cache) and case-insensitive file indexes of the base
    install, the output tree and the XML1 sources (xml1_loose wins over xml1_assets);
  * the XML1 namespace (research/characters/x1names.py + x1_namespace_map.json) as map_* helpers;
  * writers that enforce the hard format rules: XMLB attribute names lowercase + sorted, no header-only
    (8-byte) XMLB, CRLF scripts, atomic writes that can never touch the base install;
  * a registry of every file written this build (owner module, source, whether it replaced a base file)
    that enforces file ownership between modules;
  * a per-module report collector (notes / warnings / errors / deferred / counts);
  * ctx.shared, the documented hand-over dict between modules (SPEC.md section 5).

Nothing here launches the game or modifies anything outside ctx.out.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat as _stat
import sys
import threading
import time
import traceback
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# ----------------------------------------------------------------------------------------------- paths
# Developer-mode locations (Sources.developer). The pipeline reads its inputs through ctx.sources / ctx.x1_* /
# ctx.research_path, never through these constants; they stay for the standalone research / self-test tools.
from .sources import Sources, REPO_ROOT, DEFAULT_XML2, apply_collisions   # noqa: E402

ROOT = REPO_ROOT
TOOLS = ROOT / 'tools'
RESEARCH = ROOT / 'research'
X1_LOOSE = ROOT / 'xml1_loose'
X1_ASSETS = ROOT / 'xml1_assets'
X1_XBOX = ROOT / 'xml1_xbox'
DEFAULT_BASE = DEFAULT_XML2

# No sys.path set-up: tools/ is on the path wherever this package is importable (xmlb), and the research modules
# the build needs live in xml1build.lib (BUILDER_DESIGN.md 1.5; SPEC.md 27.13; their research/ files are shims).
import xmlb                    # noqa: E402  tools/xmlb.py
from .lib import sweeplib      # noqa: E402  robust XML1 text-XML parser (was research/sweep)
from .lib import x1names       # noqa: E402  skin/animdb/style namespace (was research/characters)

MODULE_ORDER = ('characters', 'heroes', 'scripts', 'zones', 'media', 'frontend')   # content modules, in run order
POST_STEPS = ('testhooks', 'validate')                          # run after the content modules
BUILD_OWNER = 'build'                                           # owner name used by build_xml1.py itself

# XML2 front-end zones the build keeps as XML2's with --frontend xml2 (never converted from XML1): XMen2.exe loads
# the main-menu backdrop itself at boot ('loadmap menu/main_back', string 0x6a3774; mainmenuexit 0x5f28a3), before
# New Game can run. The proven test copy (xml2_test) ran with XML2's files. zone -> the XML2 files kept.
# With --frontend xml1 (SPEC 21, the default) XML1's backdrop of the same name (the Cerebro room) is converted like
# any zone; use frontend_zones(ctx) / frontend_prefixes(ctx), never these constants directly.
FRONTEND_ZONES = {'menu/main_back': ('maps/menu/main_back.', 'motionpaths/menus/main_back.',
                                     'packages/generated/maps/menu/main_back.')}
FRONTEND_PREFIXES = tuple(p for ps in FRONTEND_ZONES.values() for p in ps)
# menu backdrop zones: never campaign zones in either front end (no act on entry, no campaign plan)
MENU_ZONES = tuple(FRONTEND_ZONES)
# --frontend (SPEC 21): 'xml1' = XML1's main menu, backdrop, intro, menu music, Danger Room and Review data;
# 'xml2' = XML2's front end exactly as before SPEC 21 (A/B fallback). Also $XML1BUILD_FRONTEND.
FRONTEND_MODES = ('xml1', 'xml2')
FRONTEND_ENV = 'XML1BUILD_FRONTEND'
FRONTEND_DEFAULT = 'xml1'
# SPEC 21 A.4.4: with --frontend xml1 these XML2 banks are replaced by XML1's menu music (kind 'x1' music, installed
# from the fixed-layout banks like every XML1 music bank) instead of the merged bank. XML2's banks hold only their
# one 'music/menu_a' / 'music/menu_c' sound (dumpbank), so nothing XML2 plays is lost; the credits menu plays
# music/menu_a too (0x5b1b84), as XML1's credits did. The only 'x1' banks allowed to replace an XML2 bank.
FRONTEND_MUSIC = {'menu_a': 'XML1 main-menu / credits music (SPEC 21 A.4.4)',
                  'menu_c': 'XML1 main-menu music, combat layer key (SPEC 21 A.4.4)'}
# --xp-curve (SPEC 23.1): the XP curve the game runs this build on. 'xml1' (default) = xml2-fix [Game] XPCurve=xml1
# (tools/harness.py writes it): the XP amounts the pipeline itself chooses are XML1's (Danger Room completion 0,
# XP pickups their XML1 count); 'xml2' = XMen2.exe's own curve, no XPCurve key, the XML2-scaled amounts (Danger Room
# rewardxp by XML2's reclevel curve, XP pickup 5000). Also $XML1BUILD_XP_CURVE.
XP_CURVE_MODES = ('xml1', 'xml2')
XP_CURVE_ENV = 'XML1BUILD_XP_CURVE'
XP_CURVE_DEFAULT = 'xml1'

# root-level entries of the XML2 install that belong to the xml2-fix proxy (never copied, never kept)
PROXY_PATTERNS = ('dinput.dll', 'mods', 'xml2-fix.*')
# build metadata at the root of <out>; not game files, excluded from the out index and the sweep
META_NAMES = ('_build', '_tour.json', '.codegpt-game.json')


def builder_mode(args) -> bool:
    """builder mode (args.builder_mode; tools/xml1builder, BUILDER_DESIGN.md F3 / 1.3): the xml2-fix proxy files the
    launcher / the player put into <out> (dinput.dll, xml2-fix.ini / .log, mods/) stay - kept out of the out index,
    never swept, allowed by validate V1 - and media installs the fixed music banks straight from the prepare cache
    (P5, under the builder's cache lock) instead of snapshotting them into <out>/_build/media_cache/music_fixed
    (372 MB). build_xml1.py builds (no builder_mode) behave as always."""
    return bool(getattr(args, 'builder_mode', False))


# tools/xml1builder installs a checkpoint (set_checkpoint): called with ('log', (module, msg)) for every ctx.log
# line, ('write', rel) for every file a module registers and ('sync', rel) for every base file sync_base visits. It
# counts progress and raises the builder's cancel exception (a BaseException, so the modules' `except Exception`
# handlers let it through). None (build_xml1.py) = nothing is called.
_CHECKPOINT = None


def set_checkpoint(fn):
    """install (or with None remove) the build checkpoint; returns the previous one."""
    global _CHECKPOINT
    prev, _CHECKPOINT = _CHECKPOINT, fn
    return prev


def checkpoint(kind, detail=None):
    fn = _CHECKPOINT
    if fn is not None:
        fn(kind, detail)

# XML1 text source extension -> XML2 binary extensions written for it (proven by tools/convert_zone.py:
# localized .eng -> .XMLB + .engb, non-localized .xml -> .XMLB only; XML2 itself ships 86 XMLB-only maps)
TEXT_OUT = {'.eng': ('.XMLB', '.engb'), '.xml': ('.XMLB',), '.chr': ('.CHRB',), '.nav': ('.NAVB',)}
XMLB_FAMILY = ('.xmlb', '.engb', '.chrb', '.navb', '.boyb', '.pkgb')

# spelling of top-level directories when a module creates a path the output tree does not have yet
CANON_TOP = {d.lower(): d for d in (
    'Actors', 'Automaps', 'Conversations', 'Data', 'Dialogs', 'Docs', 'Effects', 'HUD', 'Maps', 'Models',
    'MotionPaths', 'Movies', 'Packages', 'Scripts', 'Skybox', 'Sounds', 'Subtitles', 'Texs', 'Textures', 'UI')}


class WriteCheckError(OSError):
    """builder mode: a file read back after it was written into <out> does not hash to what was written (a disk
    or copy error, an antivirus program changing or quarantining it, a full volume). Names the file."""

    def __init__(self, rel, want, got, size=None):
        super().__init__(f'{rel}: read back after writing, sha1 {got} != written {want}'
                         + (f' ({size} bytes)' if size is not None else ''))
        self.rel, self.want, self.got, self.size = rel, want, got, size


class OwnershipError(RuntimeError):
    """A module tried to write a file another module owns this build (pass replace=True if intended)."""


class EmptySource(ValueError):
    """An XML1 source file is empty (0 bytes / whitespace only); nothing valid can be written from it."""


# ----------------------------------------------------------------------------------------------- basics
def norm(rel) -> str:
    """Canonical key for a relative path: forward slashes, no leading './' or '/', lower case."""
    s = str(rel).replace('\\', '/')
    while s.startswith('./'):
        s = s[2:]
    return s.lstrip('/').lower()


def split_ext(rel: str):
    """('Maps/nyc/x', '.XMLB') - like os.path.splitext but on '/' paths."""
    base, ext = os.path.splitext(str(rel).replace('\\', '/'))
    return base, ext


def is_proxy_name(name: str) -> bool:
    n = name.lower()
    return any(fnmatch.fnmatchcase(n, p) for p in PROXY_PATTERNS)


class FileIndex:
    """Case-insensitive index of a directory tree: norm(rel) -> actual relative path ('/' separators).

    exclude_top: root-level names to skip (fnmatch patterns, case-insensitive)."""

    def __init__(self, root, exclude_top=(), scan=True):
        self.root = Path(root)
        self.exclude_top = tuple(p.lower() for p in exclude_top)
        self._files = {}          # norm rel -> actual rel
        self._dirs = {}           # norm dir rel -> actual dir rel
        self._lock = threading.RLock()
        if scan:
            self.scan()

    def _excluded(self, top: str) -> bool:
        t = top.lower()
        return any(fnmatch.fnmatchcase(t, p) for p in self.exclude_top)

    def scan(self):
        with self._lock:
            self._files.clear()
            self._dirs.clear()
            if not self.root.is_dir():
                return self
            for dirpath, dirnames, filenames in os.walk(self.root):
                rel_dir = os.path.relpath(dirpath, self.root).replace(os.sep, '/')
                if rel_dir == '.':
                    rel_dir = ''
                    dirnames[:] = [d for d in dirnames if not self._excluded(d)]
                    filenames = [f for f in filenames if not self._excluded(f)]
                for d in dirnames:
                    r = f'{rel_dir}/{d}' if rel_dir else d
                    self._dirs[r.lower()] = r
                for f in filenames:
                    r = f'{rel_dir}/{f}' if rel_dir else f
                    self._files[r.lower()] = r
        return self

    def __contains__(self, rel) -> bool:
        return norm(rel) in self._files

    def __len__(self):
        return len(self._files)

    def __iter__(self):
        return iter(list(self._files.values()))

    def keys(self):
        return list(self._files.keys())

    def get(self, rel):
        """actual relative path for rel (any case), or None."""
        return self._files.get(norm(rel))

    def path(self, rel):
        """absolute Path for rel (any case), or None."""
        a = self._files.get(norm(rel))
        return self.root / a if a is not None else None

    def dir_spelling(self, rel_dir):
        return self._dirs.get(norm(rel_dir))

    def find(self, rel_noext, exts):
        """first existing actual rel among rel_noext + ext for ext in exts (case-insensitive), or None."""
        for e in exts:
            a = self._files.get(norm(str(rel_noext) + e))
            if a is not None:
                return a
        return None

    def find_all(self, rel_noext, exts):
        return [a for a in (self._files.get(norm(str(rel_noext) + e)) for e in exts) if a is not None]

    def under(self, prefix):
        """actual rels of all files under a directory prefix (e.g. 'sounds/eng/')."""
        p = norm(prefix)
        if p and not p.endswith('/'):
            p += '/'
        return [a for k, a in self._files.items() if k.startswith(p)]

    def add(self, actual_rel):
        with self._lock:
            a = str(actual_rel).replace('\\', '/').lstrip('/')
            self._files[a.lower()] = a
            parts = a.split('/')[:-1]
            for i in range(1, len(parts) + 1):
                d = '/'.join(parts[:i])
                self._dirs.setdefault(d.lower(), d)

    def discard(self, rel):
        with self._lock:
            self._files.pop(norm(rel), None)


# ----------------------------------------------------------------------------------------------- XML
def parse_x1_text(src):
    """XML1 text XML (path or bytes) -> Element (MULTI_ROOT wrapper for several top-level elements), or
    None for an empty / whitespace-only file. Uses sweeplib.parse_text_xml_robust: fixes stray '&', '<' in
    attribute values, stray '/>' tails, and lowercases + sorts attribute names (case-collision keeps the
    lowercase original's value)."""
    raw = Path(src).read_bytes() if not isinstance(src, (bytes, bytearray)) else bytes(src)
    if not raw.strip():
        return None
    return sweeplib.parse_text_xml_robust(raw)


def normalize_attrs(root):
    """XML2 attribute lookup is a binary search: every element's attribute names lowercase and sorted.
    On a case collision (e.g. PowerAttack/powerattack) the already-lowercase spelling wins. Tags keep
    their case. Returns root."""
    for el in root.iter():
        items = {}
        for k, v in el.attrib.items():
            lk = k.lower()
            if lk in items and k != lk:
                continue
            items[lk] = v if v is not None else ''
        el.attrib = dict(sorted(items.items()))
    return root


def encode_xmlb(root) -> bytes:
    """normalize_attrs + xmlb.encode, refusing header-only output and verifying the result decodes."""
    if root is None:
        raise EmptySource('no XML root')
    normalize_attrs(root)
    data = xmlb.encode(root)
    if len(data) <= 8:
        raise EmptySource('encoded XMLB is header-only')
    xmlb.decode(data)           # raises on a malformed result
    return data


def decode_xmlb(data):
    return xmlb.decode(data)


def xmlb_attr_problems(root):
    """list of '<tag>: reason' for elements whose attribute names are not lowercase+sorted."""
    out = []
    for el in root.iter():
        keys = list(el.attrib)
        if any(k != k.lower() for k in keys):
            out.append(f'<{el.tag}> non-lowercase attribute names {keys}')
        elif keys != sorted(keys):
            out.append(f'<{el.tag}> unsorted attribute names {keys}')
    return out


def iter_roots(root):
    """top-level elements (unwraps xmlb.MULTI_ROOT)."""
    return list(root) if root.tag == xmlb.MULTI_ROOT else [root]


def find_world(root):
    """the zone's <entity name="world"> element (case-insensitive name) or None."""
    for el in root.iter():
        if el.tag.lower() == 'entity' and (el.get('name') or '').lower() == 'world':
            return el
    return None


# ----------------------------------------------------------------------------------------------- scripts
def to_crlf(text: str) -> str:
    """normalise any mix of line endings to CRLF (XMen2.exe splits script files on CRLF, 0x4a1290)."""
    t = text.replace('\r\n', '\n').replace('\r', '\n')
    return t.replace('\n', '\r\n')


def script_ref(rel: str) -> str:
    """'Scripts/nyc/alison/tut1.py' | 'scripts/nyc/alison/tut1' -> 'nyc/alison/tut1' (lower, '/')."""
    r = norm(rel)
    if r.startswith('scripts/'):
        r = r[len('scripts/'):]
    if r.endswith('.py'):
        r = r[:-3]
    return r


def script_rel(ref: str) -> str:
    """'nyc/alison/tut1' -> 'Scripts/nyc/alison/tut1.py'."""
    return f'Scripts/{script_ref(ref)}.py'


# ----------------------------------------------------------------------------------------------- names
_SKIN4 = re.compile(r'\d{4}')
_LOADING = re.compile(r'(?i)^(.*textures/loading/)(\d{4})(\.igb)?$')
_UI_CHAR = re.compile(r'(?i)^(.*hud_head_|.*(?:ui/hud|ui/models)/characters/)(\d{4})(\.igb)?$')
SKIN_ATTRS = {'skin', 'monster_skin', 'actorskin', 'leaderskin', 'mutantskin'}


def map_skin(s):
    """XML1 4-digit skin 'CCVV' -> str(CCVV + 14000) (x1names.SKIN_OFFSET). Anything else unchanged
    (2-digit costume variants, 5-digit XML2 skins, names)."""
    if s is None:
        return s
    t = str(s).strip()
    return x1names.map_skin(t) if _SKIN4.fullmatch(t) else s


def map_animdb(name):
    """actors/<name> anim DB or numeric id: skins +14000, clashing XML1 anim DBs -> 'x1_'+name,
    'common'/fightstyle_*/moveset_* stay XML2's."""
    if not name:
        return name
    t = str(name).strip()
    if re.fullmatch(r'\d{5}', t):
        return t
    return x1names.map_animdb(t)


def map_powerstyle(name):
    return x1names.map_powerstyle(name) if name else name


def map_fightstyle(name):
    return x1names.map_fightstyle(name) if name else name


def map_ui_path(p):
    """hud/hud_head_<id>, ui/hud/characters/<id>, ui/models/characters/<id> (4-digit id) -> +14000."""
    return x1names.map_ui_path(p) if p else p


def map_actor_path(p):
    """'actors/5810' | 'actors/5810.igb' | 'actors/53_grso' -> mapped (extension and dir kept)."""
    return x1names.map_actor_path(p) if p else p


def map_loading_texture(p):
    """'textures/loading/3001' -> 'textures/loading/17001' (numeric loading screens follow the skin
    prefix, XMen2.exe 'textures/loading/%02d%02d' at 0x487258). Named ones are unchanged."""
    if not p:
        return p
    m = _LOADING.match(str(p).replace('\\', '/'))
    if not m:
        return p
    return m.group(1) + map_skin(m.group(2)) + (m.group(3) or '')


def map_attr(attr: str, value):
    """Rewrite one attribute value that references an XML1 character asset. Covers skin attrs (skin,
    skin_*, monster_skin, actorskin, leaderskin, mutantskin), characteranims, powerstyle, fightstyle /
    moveset1, loading, and any value that is a character HUD/UI path, an actors/ path or a numeric loading
    texture. Returns the (possibly unchanged) value."""
    if value is None or value == '':
        return value
    a = (attr or '').lower()
    v = value
    if a in SKIN_ATTRS or a.startswith('skin_'):
        return map_skin(v)
    if a == 'model' and _SKIN4.fullmatch(str(v).strip()):
        return map_skin(v)                  # numeric bolt-on / actor model = an actors/<id> skin
    if a == 'characteranims':
        return map_animdb(v)
    if a == 'powerstyle':
        return map_powerstyle(v)
    if a in ('moveset1', 'fightstyle'):
        return map_fightstyle(v)
    s = str(v).replace('\\', '/')
    if _LOADING.match(s):
        return map_loading_texture(s)
    if _UI_CHAR.match(s):
        return map_ui_path(s)
    if s.lower().startswith('actors/'):
        return map_actor_path(s)
    return v


def map_tree_refs(root) -> int:
    """apply map_attr to every attribute of every element; returns the number of values changed."""
    n = 0
    for el in root.iter():
        for k, v in list(el.attrib.items()):
            nv = map_attr(k, v)
            if nv != v:
                el.set(k, nv)
                n += 1
    return n


def pkg_name(x1_rel: str) -> str:
    """XML1 bundle path -> XML2 package filename form: lower, '/', no extension."""
    return split_ext(norm(x1_rel))[0]


def map_package_entry(kind: str, filename: str):
    """One XML1 .fb manifest entry (kind, path-with-extension) -> (kind, XML2 packagedef filename).

    actorskin/actoranimdb -> bare mapped stem ('19810', 'x1_01_cyclops'); XML2 packages use bare names and
    the engine prepends 'actors/' only when the lowercase 'actors/' is absent (0x592520 strstr).
    model hud/ui character paths -> +14000; fightstyle data/powerstyles|fightstyles/<x> -> mapped style;
    effect -> without the 'effects/' prefix (the form all 10,796 XML2 effect entries use);
    texture textures/loading/<4 digits> -> +14000. Everything else: pkg_name(filename)."""
    k = (kind or '').lower()
    f = pkg_name(filename)
    if k in ('actorskin', 'actoranimdb'):
        stem = f[len('actors/'):] if f.startswith('actors/') else f
        return kind, map_animdb(stem)
    if k == 'model' and _UI_CHAR.match(f):
        return kind, map_ui_path(f)
    if k == 'fightstyle':
        d, _, n = f.rpartition('/')
        if d == 'data/powerstyles':
            return kind, f'{d}/{map_powerstyle(n)}'
        if d == 'data/fightstyles':
            return kind, f'{d}/{map_fightstyle(n)}'
        return kind, f
    if k == 'effect':
        return kind, f[len('effects/'):] if f.startswith('effects/') else f
    if k == 'texture' and _LOADING.match(f):
        return kind, map_loading_texture(f)
    return kind, f


def char_package_rel(stats_name: str, skin: str, nc: bool = False) -> str:
    """generated/characters/<name>_<skin>[_nc] (XMen2.exe 'generated/characters/%s_%s%s', 0x68e508)."""
    return f'Packages/generated/characters/{stats_name.lower()}_{skin}{"_nc" if nc else ""}.PKGB'


# package entry kind -> files it must resolve to (checked against all of XML2's own packages)
NO_FILE_KINDS = {'combat_is', 'bigconvmap', 'sound', 'xml_talents'}


def package_entry_files(kind: str, filename: str):
    """Candidate norm() out paths a packagedef entry resolves to (any one existing is enough), or None for
    kinds that name no file (combat_is, bigconvmap, sound, xml_talents)."""
    k = (kind or '').lower()
    f = norm(filename)
    if k in NO_FILE_KINDS:
        return None
    if k in ('actorskin', 'actoranimdb'):
        b = f if f.startswith('actors/') else 'actors/' + f
        return [b if b.endswith('.igb') else b + '.igb']
    if k in ('model', 'texture'):
        return [f + '.igb']
    if k == 'effect':
        return ['effects/' + f + '.xmlb', f + '.xmlb']
    if k in ('fightstyle', 'xml', 'xml_resident', 'zonexml'):
        return [f + '.xmlb', f + '.engb']
    if k == 'characters':
        return [f + '.chrb']
    if k == 'nav':
        return [f + '.navb']
    if k == 'boy':
        return [f + '.boyb']
    if k == 'zam':
        return [f + '.zam']
    if k == 'script':
        return [f + '.py']
    if k == 'motionpath':            # 'abyss/blimp_fly_in/mp_blimp' = file motionpaths/abyss/blimp_fly_in + object
        d = f.rpartition('/')[0]
        return ['motionpaths/' + d + '.igb', 'motionpaths/' + f + '.igb']
    return [f]


# ----------------------------------------------------------------------------------------------- registry / report
class Registry:
    """Every file written into <out> this build: norm(rel) -> entry dict
    {rel, owner, source, overwrote_base, size, mtime, shared, history}."""

    def __init__(self, entries=None):
        self.entries = dict(entries or {})
        self._lock = threading.RLock()

    def get(self, rel):
        return self.entries.get(norm(rel))

    def __contains__(self, rel):
        return norm(rel) in self.entries

    def record(self, actual_rel, owner, source=None, overwrote_base=False, size=0, mtime=0.0, shared=False, sha1=None):
        """sha1: builder mode (BuildContext.check_writes) records the hash of the bytes write_bytes wrote (the
        entry has no 'sha1' key otherwise - and for copies, whose source is the reference - so build_xml1.py's
        registry is unchanged)."""
        with self._lock:
            n = norm(actual_rel)
            prev = self.entries.get(n)
            hist = list(prev.get('history', [])) if prev else []
            if prev and prev['owner'] != owner:
                hist.append(prev['owner'])
            self.entries[n] = {'rel': str(actual_rel).replace('\\', '/'), 'owner': owner,
                               'source': str(source) if source is not None else None,
                               'overwrote_base': bool(overwrote_base or (prev or {}).get('overwrote_base')),
                               'size': int(size), 'mtime': float(mtime), 'shared': bool(shared),
                               'history': hist}
            if sha1 is not None:
                self.entries[n]['sha1'] = sha1
            return self.entries[n]

    def remove(self, rel):
        with self._lock:
            self.entries.pop(norm(rel), None)

    def owned_by(self, owner):
        return {k: e for k, e in self.entries.items() if e['owner'] == owner}

    def to_json(self):
        return {'version': 1, 'entries': self.entries}

    @classmethod
    def load(cls, path):
        p = Path(path)
        if not p.is_file():
            return cls()
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            return cls(data.get('entries', {}))
        except (OSError, ValueError):
            return cls()


class Report:
    """Per-module collector. Lists are unbounded in the JSON; print_summary shows counts + first items."""

    KINDS = ('notes', 'warnings', 'errors', 'deferred')

    def __init__(self):
        self.modules = {}
        self._lock = threading.RLock()

    def mod(self, name):
        with self._lock:
            if name not in self.modules:
                self.modules[name] = {'status': 'pending', 'seconds': 0.0, 'counts': {},
                                      **{k: [] for k in self.KINDS}}
            return self.modules[name]

    def add(self, name, kind, msg):
        with self._lock:
            self.mod(name)[kind].append(str(msg))

    def count(self, name, key, n=1):
        with self._lock:
            c = self.mod(name)['counts']
            c[key] = c.get(key, 0) + n

    def set_count(self, name, key, value):
        with self._lock:
            self.mod(name)['counts'][key] = value

    def error_total(self):
        return sum(len(m['errors']) for m in self.modules.values())

    def to_json(self):
        return {'modules': self.modules,
                'totals': {k: sum(len(m[k]) for m in self.modules.values()) for k in self.KINDS}}

    def print_summary(self, out=None, show=5):
        w = (out or sys.stdout).write
        for name, m in self.modules.items():
            w(f"[{name}] {m['status']} in {m['seconds']:.1f}s: {len(m['errors'])} errors, "
              f"{len(m['warnings'])} warnings, {len(m['deferred'])} deferred, {len(m['notes'])} notes\n")
            if m['counts']:
                w('    counts: ' + ', '.join(f'{k}={v}' for k, v in m['counts'].items()) + '\n')
            for kind in ('errors', 'warnings'):
                for msg in m[kind][:show]:
                    w(f'    {kind[:-1]}: {msg}\n')
                if len(m[kind]) > show:
                    w(f'    ... {len(m[kind]) - show} more {kind}\n')


@dataclass
class ImportResult:
    """Outcome of ctx.import_x1_asset.
    status: 'written' (in <out> from XML1, this call or an earlier identical import), 'kept_xml2' (the base
    install has that path; XML2's file is used), 'missing' (not on the XML1 disc), 'empty' (0-byte source,
    nothing written), 'skipped' (.fre/.ger: English build only), 'conflict' (another module wrote that
    path from a different source / patch; error logged)."""
    x1_rel: str
    status: str
    pkg_name: str
    out_rels: list = field(default_factory=list)

    @property
    def ok(self):
        return self.status in ('written', 'kept_xml2')


FORCED_TEAMS_MODES = ('seat', 'menu')
XML2FIX_API_JSON = 'scripts/xml2fix_api.json'     # under research/: the xml2-fix script functions (SPEC 19)


def forced_teams_mode(ctx) -> str:
    """--forced-teams (SPEC 19): 'seat' (default) = mission starts carry the xml2-fix seat block with the team menu
    as its else branch (the ini switch [Game] ForcedTeams=1 picks XML1's parties); 'menu' = no xml2-fix call at
    all (the team menu only, the port before SPEC 19)."""
    m = str((ctx.opt('forced_teams') if hasattr(ctx, 'opt') else None) or
            os.environ.get('XML1BUILD_FORCED_TEAMS') or 'seat').lower()
    return m if m in FORCED_TEAMS_MODES else 'seat'


def frontend_mode(ctx) -> str:
    """--frontend (SPEC 21): 'xml1' (default; XML1's front end, Danger Room and Review data) or 'xml2' (XML2's
    front end exactly as before SPEC 21). ctx.args.frontend, else $XML1BUILD_FRONTEND, else FRONTEND_DEFAULT."""
    m = str((ctx.opt('frontend') if hasattr(ctx, 'opt') else None) or os.environ.get(FRONTEND_ENV) or
            FRONTEND_DEFAULT).lower()
    return m if m in FRONTEND_MODES else FRONTEND_DEFAULT


def xp_curve_mode(ctx) -> str:
    """--xp-curve (SPEC 23.1): 'xml1' (default; XML1's level table through xml2-fix, XML1's XP amounts) or 'xml2'
    (XMen2.exe's curve, XML2-scaled amounts). ctx.args.xp_curve, else $XML1BUILD_XP_CURVE, else XP_CURVE_DEFAULT."""
    m = str((ctx.opt('xp_curve') if hasattr(ctx, 'opt') else None) or os.environ.get(XP_CURVE_ENV) or
            XP_CURVE_DEFAULT).lower()
    return m if m in XP_CURVE_MODES else XP_CURVE_DEFAULT


def frontend_zones(ctx) -> dict:
    """the XML2 front-end zones this build keeps as XML2's (FRONTEND_ZONES with --frontend xml2, none with xml1)."""
    return FRONTEND_ZONES if frontend_mode(ctx) == 'xml2' else {}


def frontend_prefixes(ctx) -> tuple:
    """norm path prefixes of the XML2 front-end files this build keeps (empty with --frontend xml1)."""
    return FRONTEND_PREFIXES if frontend_mode(ctx) == 'xml2' else ()


def build_options(out) -> dict:
    """the 'build' block of <out>/_build/report.json (the options the build in <out> was made with), or {}.
    Standalone tools (self-tests, validate over an existing tree) use it to rebuild ctx.args as the build had them."""
    try:
        b = json.loads((Path(out) / '_build' / 'report.json').read_text(encoding='utf-8')).get('build')
    except (OSError, ValueError, AttributeError):
        return {}
    return b if isinstance(b, dict) else {}


def args_for_out(out, base=None, **kw):
    """default_args for an existing build in <out>, with the content options its report.json recorded (frontend,
    forced_teams, no_movies, ...), so a standalone check sees the build as it was made. kw overrides."""
    b = build_options(out)
    keep = {k: b[k] for k in ('frontend', 'forced_teams', 'no_movies', 'newgame', 'blackbird', 'npc_scaling',
                              'tiles', 'hero_roster', 'hero_icons', 'hero_bleed', 'start_zone', 'tour', 'xp_curve')
            if k in b and b[k] is not None}
    if 'frontend' not in b and b:
        keep['frontend'] = 'xml2'            # a build made before SPEC 21 had XML2's front end
    if 'xp_curve' not in b and b:
        keep['xp_curve'] = 'xml2'            # a build made before SPEC 23.1 carried the XML2-scaled amounts
    keep.update(kw)
    return default_args(out=str(out), base=str(base or DEFAULT_BASE), **keep)


def map_review_texture(ctx, p):
    """SPEC 21 C.4.2 (pure): the XML2 path of an XML1 review / imageViewer / loading texture reference under
    --frontend xml1 (lowercase, '/', no extension):
      textures/comic/<x>[.png]  -> textures/comic/x1/<x>   (XML2 ships rogue_cov / storm_cov; the path keeps "comic",
                                   the imageViewer rule 0x49e440); the XML1 Colossus pickup's 'comic/0901' (no such
                                   texture; its review value is col_cov) -> textures/comic/x1/col_cov
      textures/concept/<y>      -> textures/concept/x1/<y> (27 collide with XML2; keeps "concept")
      textures/loading/<dddd>   -> map_loading_texture (+14000)
      textures/loading/<name>   -> textures/loading/x1_<name> when XML2 ships a texture of that name (x_jet,
                                   characters_menu), else unchanged
    Anything else (and every path with --frontend xml2): norm'd, extension stripped, otherwise unchanged."""
    if not p:
        return p
    s = norm(p)
    base, ext = split_ext(s)
    if ext in ('.png', '.igb', '.tga', '.bmp'):
        s = base
    if frontend_mode(ctx) != 'xml1':
        return s
    for kind in ('comic', 'concept'):
        pre = f'textures/{kind}/'
        if s.startswith(pre) and not s.startswith(pre + 'x1/'):
            stem = s[len(pre):]
            if kind == 'comic' and stem in REVIEW_TEXTURE_FIXES:
                stem = REVIEW_TEXTURE_FIXES[stem]
            return f'{pre}x1/{stem}'
    if s.startswith('textures/loading/'):
        m = map_loading_texture(s)
        if m != s:
            return m
        stem = s[len('textures/loading/'):]
        if '/' not in stem and not stem.startswith('x1_') and ctx.base_index.find(s, ('.IGB', '.png', '.tga')):
            return f'textures/loading/x1_{stem}'
    return s


# XML1 data quirk (M2_DESIGN C.1): muir_in3's Colossus comic pickup calls imageViewer('textures/comic/0901.png'),
# but XML1's review value is textures/comic/col_cov and no comic/0901 texture exists on the disc
REVIEW_TEXTURE_FIXES = {'0901': 'col_cov'}
# SPEC 21 A.4.1 (--frontend xml1): the loading screen of the main-menu backdrop (XML1's zoneinfo has no entry for
# menu/main_back; XML2's shows its own main_menu image). XML1's Xavier Institute screen (Owen's decision E.3).
FRONTEND_MENU_LOADING = 'textures/loading/x_mansion'


def x1_loading_source(p):
    """'textures/loading/x1_<name>' (a renamed XML1 screen, map_review_texture) -> 'textures/loading/<name>', the
    XML1 source path; None for any other path."""
    s = norm(p)
    pre = 'textures/loading/x1_'
    if s.startswith(pre) and '/' not in s[len(pre):]:
        return 'textures/loading/' + split_ext(s[len(pre):])[0]
    return None


def default_args(**kw):
    """argparse.Namespace with every option build_xml1.py defines (for tests / module-level use)."""
    a = dict(out=None, base=str(DEFAULT_BASE), start_zone=None, tour=None, no_movies=False, only=None,
             no_validate=False, test_ini=False, adopt=False, jobs=max(1, (os.cpu_count() or 2) // 2))
    a.update(kw)
    return argparse.Namespace(**a)


# ----------------------------------------------------------------------------------------------- context
class BuildContext:
    """The object every module's run(ctx) receives. See SPEC.md section 3 for the contract.

    sources (xml1build.sources.Sources): where the inputs live. None = the Sources the build in <out> was made with
    (<out>/_build/sources.json of a prepared build), else developer mode (the repo's folders) - so standalone
    checks and self-tests over an existing build read the same inputs the build read."""

    def __init__(self, out, base=DEFAULT_BASE, args=None, registry=None, scan_out=True, sources=None):
        self.args = args or default_args(out=str(out), base=str(base))
        self.sources = sources if sources is not None else Sources.for_out(out, base)
        apply_collisions(self.sources)               # x1names' every map_* rename reads this collisions.json
        self.root, self.tools, self.research = self.sources.root, self.sources.root / 'tools', self.sources.research
        src = self.sources
        self.x1_loose, self.x1_assets, self.x1_xbox = src.x1_loose, src.x1_assets, src.x1_xbox
        self.out = Path(out).resolve()
        self.base = Path(base).resolve()
        self.build_dir = self.out / '_build'
        _check_out_safe(self.out, self.base, self.sources.protected())
        self.base_index = FileIndex(self.base, exclude_top=PROXY_PATTERNS)
        self.out_index = FileIndex(self.out, exclude_top=META_NAMES + (PROXY_PATTERNS if builder_mode(self.args) else ()),
                                   scan=scan_out)
        self.x1_loose_index = FileIndex(self.x1_loose, exclude_top=('_fb_manifest.json',))
        self.x1_assets_index = FileIndex(self.x1_assets)
        self.registry = registry if registry is not None else Registry()
        self.check_writes = builder_mode(self.args)    # the sha1 of every file written from memory
        self.report = Report()
        self.shared = {}
        self.module = BUILD_OWNER
        self._lock = threading.RLock()
        self._imports = {}
        self._json = {}
        self._sound_plan = None
        self._weapon_models = None
        self.schema_log = {}                 # x1schema change kind -> {x1 rel: count} (every module's imports)

    # ------------------------------------------------------------------ options / logging / report
    def opt(self, name, default=None):
        return getattr(self.args, name, default)

    def log(self, msg):
        print(f'[{self.module}] {msg}', flush=True)
        checkpoint('log', (self.module, msg))

    def note(self, msg):
        self.report.add(self.module, 'notes', msg)

    def warn(self, msg):
        self.report.add(self.module, 'warnings', msg)

    def error(self, msg):
        self.report.add(self.module, 'errors', msg)

    def defer(self, msg):
        """something intentionally left for a later phase (hero conversion, powers rework, ...)."""
        self.report.add(self.module, 'deferred', msg)

    def count(self, key, n=1):
        self.report.count(self.module, key, n)

    def set_count(self, key, value):
        self.report.set_count(self.module, key, value)

    # ------------------------------------------------------------------ research data (cached, read-only)
    def research_path(self, rel) -> Path:
        """where the research input `rel` lives ('scripts/out/scripts', 'sound/out/all_ima/eng', ...): research/<rel>
        in developer mode; a prepared stage's output when the Sources override it (Sources.research_path)."""
        return self.sources.research_path(rel)

    def research_json(self, rel):
        """json.load of the research input <rel> (e.g. 'sweep/graph.json'; research_path), cached."""
        if rel not in self._json:
            self._json[rel] = json.loads(self.research_path(rel).read_text(encoding='utf-8'))
        return self._json[rel]

    @property
    def manifest(self):
        """xml1_loose/_fb_manifest.json: bundle path ('packages/generated/maps/<zone>.fb') -> [[path, kind]]."""
        if 'manifest' not in self._json:
            self._json['manifest'] = json.loads((self.x1_loose / '_fb_manifest.json').read_text(encoding='utf-8'))
        return self._json['manifest']

    @property
    def nsmap(self):
        """research/characters/x1_namespace_map.json (skins, animdbs, powerstyles, fightstyles, ...)."""
        return self.research_json('characters/x1_namespace_map.json')

    @property
    def collisions(self):
        """research/sweep/collisions.json 'files': XML1 rel -> {'status': new|different|identical, 'xml2': [...]}"""
        return self.research_json('sweep/collisions.json')['files']

    @property
    def graph(self):
        return self.research_json('sweep/graph.json')

    @property
    def zones_info(self):
        """research/sweep/zones.json: zone -> {category, chr_characters, links, ...}"""
        return self.research_json('sweep/zones.json')

    @property
    def xml2_api(self):
        """research/scripts/xml2_api.json: script function name (exact case) -> {args, ret, func, table}. In a
        --forced-teams seat build (SPEC 19) the xml2-fix functions of research/scripts/xml2fix_api.json are merged
        in: scripts call them only behind the xml2fixFeature guard (validate V14b), and without the DLL the engine
        drops those statements, so the checks treat them as registered."""
        if forced_teams_mode(self) != 'seat':
            return self.research_json('scripts/xml2_api.json')
        key = '_xml2_api_forced'
        if key not in self._json:
            api = dict(self.research_json('scripts/xml2_api.json'))
            for name, e in self.research_json(XML2FIX_API_JSON)['functions'].items():
                api.setdefault(name, dict(e))
            self._json[key] = api
        return self._json[key]

    def x1_zones(self):
        """all 210 XML1 zone paths (lowercase, '/'), from the map bundles outside maps/package/."""
        pre, suf = 'packages/generated/maps/', '.fb'
        return sorted(k[len(pre):-len(suf)] for k in self.manifest
                      if k.startswith(pre) and k.endswith(suf) and not k.startswith(pre + 'package/'))

    def zone_bundle(self, zone):
        """[[path, kind], ...] of an XML1 zone bundle ('nyc/alison/nyc1_1_1')."""
        return self.manifest[f'packages/generated/maps/{norm(zone)}.fb']

    def tour_order(self):
        """research/sweep/graph.json reachable_from_new_game (162 zones, BFS order from New Game)."""
        return list(self.graph['reachable_from_new_game'])

    # ------------------------------------------------------------------ XML1 sources
    def x1_path(self, rel):
        """absolute Path of an XML1 source (xml1_loose wins over xml1_assets), or None."""
        return self.x1_loose_index.path(rel) or self.x1_assets_index.path(rel)

    def x1_origin(self, rel):
        if rel in self.x1_loose_index:
            return 'loose'
        if rel in self.x1_assets_index:
            return 'assets'
        return None

    def x1_rels(self, prefix=''):
        """norm() rels of XML1 files under prefix, loose and assets merged (assets' .fb bundles excluded)."""
        keys = set(k for k in self.x1_loose_index.keys())
        keys |= {k for k in self.x1_assets_index.keys() if not k.startswith('packages/generated/')}
        p = norm(prefix)
        return sorted(k for k in keys if k.startswith(p))

    def x1_is_empty(self, rel):
        p = self.x1_path(rel)
        return p is not None and (p.stat().st_size == 0 or not p.read_bytes().strip())

    def read_x1_xml(self, rel):
        """XML1 text XML -> Element (attribute names lowercased+sorted), None if empty; KeyError if missing."""
        p = self.x1_path(rel)
        if p is None:
            raise KeyError(f'XML1 has no {rel}')
        return parse_x1_text(p)

    def weapon_models(self):
        """lower XML1 weapon name -> model path (xml1 data/weapons/weapons.eng), cached; used by x1schema to give
        a remapped scan turret its turret weapon's model."""
        if self._weapon_models is None:
            wm = {}
            try:
                root = self.read_x1_xml('data/weapons/weapons.eng')
            except KeyError:
                root = None
            if root is not None:
                for w in root.iter():
                    if w.tag.lower() == 'weapon' and w.get('name') and w.get('model'):
                        # weapons name the file ('models/haarp/tank_turret_haarp'); an entity 'model' attribute is
                        # relative to models/ ('haarp/workbench'), as in every XML1 and XML2 physent
                        m = w.get('model').strip().replace('\\', '/').lower()
                        wm[w.get('name').strip().lower()] = m[len('models/'):] if m.startswith('models/') else m
            self._weapon_models = wm
        return self._weapon_models

    def x1_schema(self, root, x1_rel):
        """Apply xml1build.x1schema.convert (XML1 -> XML2 entity classes / renamed attributes / effect colours)
        to an XML1 text tree in place and log the changes in ctx.schema_log. Every XML1 text file the build
        writes goes through this (import_x1_asset calls it; modules that write XML1 trees themselves call it)."""
        from . import x1schema
        ch = x1schema.convert(root, x1_rel, self.weapon_models())
        if ch:
            key = norm(x1_rel)
            with self._lock:
                for k, v in ch.items():
                    self.schema_log.setdefault(k, {})
                    self.schema_log[k][key] = v
        return ch

    def read_base_xmlb(self, rel):
        p = self.base_index.path(rel)
        if p is None:
            raise KeyError(f'base install has no {rel}')
        return decode_xmlb(p.read_bytes())

    def read_out_xmlb(self, rel):
        """current state of an XMLB-family file in <out> (base copy or this build's output)."""
        p = self.out_index.path(rel)
        if p is None:
            raise KeyError(f'<out> has no {rel}')
        return decode_xmlb(p.read_bytes())

    def out_exists(self, rel):
        return rel in self.out_index

    def base_exists(self, rel):
        return rel in self.base_index

    # ------------------------------------------------------------------ writing
    def out_path(self, rel) -> Path:
        """absolute path inside <out> for rel, reusing the existing spelling of every existing directory
        (and the file itself) so case-only variants never appear; new top dirs use XML2's spelling."""
        clean = str(rel).replace('\\', '/').lstrip('/')
        existing = self.out_index.get(clean)
        if existing:
            return self.out / existing
        parts = clean.split('/')
        acc = []
        for i, part in enumerate(parts[:-1]):
            cand = '/'.join(acc + [part])
            sp = self.out_index.dir_spelling(cand)
            if sp is not None:
                acc = sp.split('/')
            elif i == 0 and part.lower() in CANON_TOP:
                acc = [CANON_TOP[part.lower()]]
            else:
                acc.append(part)
        p = (self.out / '/'.join(acc + [parts[-1]])).resolve()
        if self.out not in p.parents:
            raise ValueError(f'refusing to write outside <out>: {rel}')
        return p

    def _claim(self, rel, replace):
        prev = self.registry.get(rel)
        if prev and prev['owner'] != self.module and not replace:
            raise OwnershipError(f'{rel}: owned by module {prev["owner"]!r}, write attempted by {self.module!r}')
        return prev

    def _finish(self, path: Path, source, shared=False, sha1=None):
        actual = path.relative_to(self.out).as_posix()
        st = path.stat()
        overwrote = actual in self.base_index
        self.out_index.add(actual)
        self.registry.record(actual, self.module, source=source, overwrote_base=overwrote,
                             size=st.st_size, mtime=st.st_mtime, shared=shared, sha1=sha1)
        checkpoint('write', actual)
        return actual

    def write_bytes(self, rel, data: bytes, *, source=None, replace=False, shared=False) -> str:
        """Write a file into <out> atomically (temp + os.replace, so a hard link into the base install can never
        be written through). replace=True is required to overwrite a file another module wrote this build;
        overwriting a base-install file needs no flag (it is recorded as overwrote_base). Returns actual rel.
        Builder mode (check_writes): the registry records the sha1 of the bytes written; the builder reads every
        file back against it before the build is stamped."""
        with self._lock:
            self._claim(rel, replace)
            path = self.out_path(rel)
            _atomic_write(path, data)
            digest = hashlib.sha1(data).hexdigest() if self.check_writes else None
            return self._finish(path, source, shared, sha1=digest)

    def copy_file(self, src, rel, *, replace=False, shared=False) -> str:
        """Copy a source file into <out> (shutil.copy2). Skips the copy when the destination already has the
        same size and mtime (a previous build's identical copy); still registers it (with its source: builder
        mode checks every copy against its source's sha1 before the build is stamped, and copies it again when
        they differ)."""
        src = Path(src)
        with self._lock:
            self._claim(rel, replace)
            path = self.out_path(rel)
            s = src.stat()
            if path.is_file():
                d = path.stat()
                if d.st_size == s.st_size and int(d.st_mtime) == int(s.st_mtime) and \
                        not path.samefile(src):
                    return self._finish(path, src, shared)
            _atomic_copy(src, path)
            return self._finish(path, src, shared)

    def write_xmlb(self, rel_noext, root, exts=('.XMLB',), *, source=None, replace=False, shared=False):
        """Encode once (encode_xmlb: attrs lowercase+sorted, never header-only) and write rel_noext + ext for
        each ext (use ('.XMLB', '.engb') for localized files). Returns the list of actual rels."""
        data = encode_xmlb(root)
        return [self.write_bytes(str(rel_noext) + e, data, source=source, replace=replace, shared=shared)
                for e in exts]

    def write_xmlb_pair(self, rel_noext, root_xmlb, root_engb, *, source=None, replace=False):
        """For tables XML2 ships as two DIFFERENT files (npcstat, herostat, zoneinfo, strings, items, ...:
        XMLB carries @DATA@ keys, engb English text): write each from its own tree."""
        return [self.write_bytes(f'{rel_noext}.XMLB', encode_xmlb(root_xmlb), source=source, replace=replace),
                self.write_bytes(f'{rel_noext}.engb', encode_xmlb(root_engb), source=source, replace=replace)]

    def write_script(self, rel, text, *, source=None, replace=False) -> str:
        """Write a script file with CRLF line endings (latin-1). rel: 'Scripts/<...>.py' or a script ref
        ('x1/tour/nyc/alison/nyc1_1_1'). Lines may not contain NUL."""
        if isinstance(text, (list, tuple)):
            text = '\r\n'.join(text) + '\r\n'
        r = str(rel).replace('\\', '/')
        if not r.lower().endswith('.py'):
            r = script_rel(r)
        elif not r.lower().startswith('scripts/'):
            r = 'Scripts/' + r
        return self.write_bytes(r, to_crlf(text).encode('latin-1'), source=source, replace=replace)

    def write_json(self, rel, obj, *, replace=False) -> str:
        return self.write_bytes(rel, json.dumps(obj, indent=1, sort_keys=False).encode('utf-8'), replace=replace)

    def write_meta(self, name, obj):
        """Build metadata (reports, intermediate JSON) -> <out>/_build/<name>; not a game file, not registered."""
        p = self.build_dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        data = obj if isinstance(obj, (bytes, bytearray)) else json.dumps(obj, indent=1, default=str).encode('utf-8')
        _atomic_write(p, bytes(data))
        return p

    def patch_out_xmlb(self, rel_noext, fn, exts=('.XMLB', '.engb', '.CHRB', '.PKGB'), *, replace=True):
        """Decode every existing rel_noext+ext in <out>, call fn(root) -> bool changed, re-encode and write
        the changed ones. Returns the list of actual rels rewritten. Used by testhooks (zonescript patch)
        and for read-modify-write of base tables."""
        done = []
        for e in exts:
            actual = self.out_index.get(str(rel_noext) + e)
            if actual is None:
                continue
            root = decode_xmlb((self.out / actual).read_bytes())
            if fn(root):
                done.append(self.write_bytes(actual, encode_xmlb(root), replace=replace))
        return done

    def remove_out(self, rel):
        """Delete a file this build wrote (owner only). Base files cannot be removed."""
        with self._lock:
            prev = self.registry.get(rel)
            if prev is None or prev['owner'] != self.module:
                raise OwnershipError(f'{rel}: not written by {self.module!r}')
            if rel in self.base_index:
                raise OwnershipError(f'{rel}: is a base-install file')
            p = self.out_index.path(rel)
            if p and p.exists():
                p.unlink()
            self.out_index.discard(rel)
            self.registry.remove(rel)

    # ------------------------------------------------------------------ XML1 asset import (shared)
    def import_x1_asset(self, x1_rel, *, force=False, patch=None, patch_key=None, out_rel_noext=None,
                        out_ext=None) -> ImportResult:
        """Bring one XML1 file into <out> under the collision policy (SPEC.md 4.4) and return where it is.

        * text XML (.eng/.xml/.chr/.nav) -> XMLB family per TEXT_OUT via parse_x1_text + encode_xmlb;
          patch(root) may modify the tree first (return value ignored). Give deterministic patches a
          patch_key (e.g. 'zones.data') so repeated imports of the same file are cached.
        * any other file -> byte copy ('.igb' written as '.IGB'); 0-byte sources -> status 'empty'.
        * scripts (.py) are NOT imported here: the scripts module installs the rewritten scripts.
        * if the base install already has the output path and force is False -> 'kept_xml2' (XML2 wins).
        * idempotent: a second identical import (same source, same patch_key or no patch) returns the first
          result, whichever module did it; the file stays owned by the first importer and is marked shared.
          The same module re-importing with a patch rewrites its own file; a DIFFERENT module importing an
          already written path with a different patch gets status 'conflict' (+ error) unless force.
        out_rel_noext overrides the destination (e.g. mapped names); pkg_name is always the lower,
        extensionless destination path."""
        n = norm(x1_rel)
        stem, ext = split_ext(n)
        if ext == '.py':
            raise ValueError(f'{x1_rel}: scripts are installed by the scripts module, not import_x1_asset')
        dst_noext = str(out_rel_noext).replace('\\', '/') if out_rel_noext else stem
        key = (n, norm(dst_noext), force, patch_key if patch is not None else None)
        cacheable = patch is None or patch_key is not None
        with self._lock:
            if cacheable and key in self._imports:
                return self._imports[key]
            src = self.x1_path(n)
            res = self._import(n, src, ext, dst_noext, force, patch, out_ext)
            if cacheable:
                self._imports[key] = res
            return res

    def _import(self, n, src, ext, dst_noext, force, patch, out_ext):
        pname = norm(dst_noext)
        if ext in ('.fre', '.ger'):
            return ImportResult(n, 'skipped', pname)          # English build only (SPEC.md 0)
        if src is None:
            return ImportResult(n, 'missing', pname)
        if ext in TEXT_OUT:
            exts = TEXT_OUT[ext]
        else:
            exts = (out_ext or ('.IGB' if ext == '.igb' else ext),)
        if not force:
            kept = self.base_index.find_all(dst_noext, exts)
            if kept:
                return ImportResult(n, 'kept_xml2', pname, kept)
        # already written this build by someone?
        prior = [self.registry.get(dst_noext + e) for e in exts]
        if all(prior):
            same_src = all(p['source'] == str(src) for p in prior)
            if same_src and patch is None:
                return ImportResult(n, 'written', pname, [p['rel'] for p in prior])
            if same_src and all(p['owner'] == self.module for p in prior):
                pass                                    # same module, patched again: rewrite below
            elif not force:
                self.error(f'{n}: {dst_noext} already written by {prior[0]["owner"]} from {prior[0]["source"]}')
                return ImportResult(n, 'conflict', pname, [p['rel'] for p in prior])
        if src.stat().st_size == 0:
            return ImportResult(n, 'empty', pname)
        if ext in TEXT_OUT:
            root = parse_x1_text(src)
            if root is None:
                return ImportResult(n, 'empty', pname)
            self.x1_schema(root, n)             # XML1 -> XML2 schema (entity classes, effect colours), x1schema.py
            if patch is not None:
                patch(root)
            rels = self.write_xmlb(dst_noext, root, exts, source=src, shared=True, replace=force)
        else:
            rels = [self.copy_file(src, dst_noext + exts[0], shared=True, replace=force)]
        return ImportResult(n, 'written', pname, rels)

    # ------------------------------------------------------------------ name mapping (thin wrappers)
    map_skin = staticmethod(map_skin)
    map_animdb = staticmethod(map_animdb)
    map_powerstyle = staticmethod(map_powerstyle)
    map_fightstyle = staticmethod(map_fightstyle)
    map_ui_path = staticmethod(map_ui_path)
    map_actor_path = staticmethod(map_actor_path)
    map_loading_texture = staticmethod(map_loading_texture)
    map_attr = staticmethod(map_attr)
    map_tree_refs = staticmethod(map_tree_refs)
    map_package_entry = staticmethod(map_package_entry)
    char_package_rel = staticmethod(char_package_rel)
    package_entry_files = staticmethod(package_entry_files)

    # ------------------------------------------------------------------ sound bank plan
    def planned_sound_banks(self):
        """Every ZSND bank <out>/Sounds/eng will contain once media has run (pure; usable before media runs):
        norm(rel) -> {'bank': stem, 'kind': 'base'|'x1'|'merged', 'src': Path|None}.

        XML1 banks come from research/sound/out/all_ima/eng (all 216 converted, char/ aliases added). A bank
        whose stem (any extension) exists in XML2 is taken from research/sound/out/merged/eng (XML2 entries
        win) or, when no merged version exists (bishop_m: empty in XML1), XML2's file is kept. With --frontend
        xml1 the FRONTEND_MUSIC banks (menu_a / menu_c) are XML1's own ('x1', 'frontend': True; SPEC 21)."""
        if self._sound_plan is not None:
            return self._sound_plan
        plan = {}
        base_by_stem = {}
        for a in self.base_index.under('sounds/eng/'):
            s, e = split_ext(a)
            if e.lower() in ('.zsm', '.zss'):
                plan[norm(a)] = {'bank': Path(s).name.lower(), 'kind': 'base', 'src': None}
                base_by_stem.setdefault(Path(s).name.lower(), []).append(norm(a))
        ima = self.research_path('sound/out/all_ima/eng')
        merged = self.research_path('sound/out/merged/eng')
        x1_menu_music = frontend_mode(self) == 'xml1'
        for dirpath, _, files in os.walk(ima):
            for f in files:
                s, e = os.path.splitext(f)
                if f.startswith('_') or e.lower() not in ('.zsm', '.zss'):
                    continue
                src = Path(dirpath) / f
                sub = src.relative_to(ima).as_posix()
                rel = norm('sounds/eng/' + sub)
                stem = s.lower()
                if x1_menu_music and stem in FRONTEND_MUSIC and e.lower() == '.zss':
                    # SPEC 21 A.4.4: XML1's menu music replaces XML2's bank (media installs the fixed-layout bank)
                    for old in base_by_stem.get(stem, []):
                        plan.pop(old, None)
                    plan[rel] = {'bank': stem, 'kind': 'x1', 'src': src, 'frontend': True}
                    continue
                if stem in base_by_stem:
                    m = merged / sub
                    if m.is_file():
                        for old in base_by_stem[stem]:
                            plan.pop(old, None)
                        plan[rel] = {'bank': stem, 'kind': 'merged', 'src': m}
                    continue
                plan[rel] = {'bank': stem, 'kind': 'x1', 'src': src}
        self._sound_plan = plan
        return plan

    def sound_bank_rel(self, bank):
        """norm rel of the planned bank named `bank` (sounddir/soundfile bank, e.g. 'grso_m', 'nyc1_m'),
        preferring .zsm (the loader opens .zsm first, 0x591380), or None."""
        b = str(bank).lower()
        hits = sorted((r for r, v in self.planned_sound_banks().items() if v['bank'] == b),
                      key=lambda r: not r.endswith('.zsm'))
        return hits[0] if hits else None


# ----------------------------------------------------------------------------------------------- file ops
def sha1_file(path) -> str:
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _make_writable(path: Path):
    try:
        mode = path.stat().st_mode
        if not mode & _stat.S_IWRITE:
            os.chmod(path, mode | _stat.S_IWRITE)
    except FileNotFoundError:
        pass


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.tmp{os.getpid()}_{threading.get_ident()}')
    with open(tmp, 'wb') as f:
        f.write(data)
    _make_writable(path)
    os.replace(tmp, path)


def _atomic_copy(src: Path, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.tmp{os.getpid()}_{threading.get_ident()}')
    shutil.copy2(src, tmp)
    _make_writable(tmp)
    _make_writable(path)
    os.replace(tmp, path)


def _check_out_safe(out: Path, base: Path, protected_trees=None):
    """<out> may never be (inside) the base install, and never inside the protected source trees (the Sources'
    inputs, research/, tools/, the prepare cache; default: the developer-mode folders)."""
    out, base = out.resolve(), base.resolve()
    if out == base or base in out.parents:
        raise ValueError(f'--out {out} is the base install or inside it')
    if out in base.parents:
        raise ValueError(f'--out {out} contains the base install')
    if protected_trees is None:
        protected_trees = (X1_LOOSE, X1_ASSETS, X1_XBOX, RESEARCH, TOOLS)
    for protected in protected_trees:
        pr = protected.resolve()
        if out == pr or pr in out.parents or out in pr.parents:
            raise ValueError(f'--out {out} overlaps protected tree {pr}')
    if len(out.parts) <= 1:
        raise ValueError(f'--out {out} is a drive root')


def sync_base(base, out, *, skip_sfd=False, keep=(), log=print):
    """Make <out> a copy of the base install minus the xml2-fix proxy (and minus *.sfd when skip_sfd),
    leaving every norm() rel in `keep` untouched (outputs carried over from a previous build of modules that
    are not re-run). Copies only files whose size or mtime differ, so a rebuild into the same <out> restores
    every base file a previous build replaced. Extra files are removed later by sweep_stale()."""
    base, out = Path(base), Path(out)
    keep = set(keep)
    st = {'copied': 0, 'unchanged': 0, 'kept': 0, 'bytes': 0}
    t0 = time.time()
    for dirpath, dirnames, filenames in os.walk(base):
        rel_dir = os.path.relpath(dirpath, base).replace(os.sep, '/')
        if rel_dir == '.':
            rel_dir = ''
            dirnames[:] = [d for d in dirnames if not is_proxy_name(d)]
            filenames = [f for f in filenames if not is_proxy_name(f)]
        for f in filenames:
            if skip_sfd and f.lower().endswith('.sfd'):
                continue
            rel = f'{rel_dir}/{f}' if rel_dir else f
            checkpoint('sync', rel)
            if norm(rel) in keep:
                st['kept'] += 1
                continue
            src = Path(dirpath) / f
            dst = out / rel
            s = src.stat()
            if dst.is_file():
                d = dst.stat()
                if d.st_size == s.st_size and int(d.st_mtime) == int(s.st_mtime):
                    st['unchanged'] += 1
                    continue
            _atomic_copy(src, dst)
            st['copied'] += 1
            st['bytes'] += s.st_size
    st['seconds'] = round(time.time() - t0, 1)
    log(f'[build] base sync: {st}')
    return st


def sweep_stale(out, base_index: FileIndex, registry: Registry, *, skip_sfd=False, log=print, keep_proxy=False,
                failed=None):
    """Delete every file in <out> that is neither a base-install file (minus *.sfd when skip_sfd, minus the
    proxy) nor registered this build (incl. carried-over entries), then remove directories left empty that
    the base does not have. Build metadata (META_NAMES) is kept; with keep_proxy (builder mode) the xml2-fix proxy
    files at the root (PROXY_PATTERNS: dinput.dll, xml2-fix.*, mods/) are kept too. Returns the removed rels;
    failed (a dict) gets {rel: OSError} of the files that could not be deleted (held open by another program)."""
    out = Path(out)
    removed = []
    for dirpath, dirnames, filenames in os.walk(out):
        rel_dir = os.path.relpath(dirpath, out).replace(os.sep, '/')
        if rel_dir == '.':
            rel_dir = ''
            dirnames[:] = [d for d in dirnames if d.lower() not in META_NAMES and not (keep_proxy and is_proxy_name(d))]
            filenames = [f for f in filenames if f.lower() not in META_NAMES and not (keep_proxy and is_proxy_name(f))]
        for f in filenames:
            rel = f'{rel_dir}/{f}' if rel_dir else f
            n = norm(rel)
            if n in registry:
                continue
            if n in base_index and not (skip_sfd and n.endswith('.sfd')):
                continue
            try:
                (Path(dirpath) / f).unlink()
                removed.append(rel)
            except OSError as e:
                log(f'[build] sweep: cannot remove {rel}: {e}')
                if failed is not None:
                    failed[rel] = e
    for dirpath, dirnames, filenames in os.walk(out, topdown=False):
        rel_dir = os.path.relpath(dirpath, out).replace(os.sep, '/')
        if rel_dir == '.' or rel_dir.split('/')[0].lower() in META_NAMES:
            continue
        if keep_proxy and is_proxy_name(rel_dir.split('/')[0]):
            continue
        if base_index.dir_spelling(rel_dir) is None:
            try:
                os.rmdir(dirpath)
            except OSError:
                pass
    if removed:
        log(f'[build] sweep: removed {len(removed)} stale files')
    return removed


def run_step(ctx: BuildContext, name: str, fn):
    """Run fn(ctx) as module `name` with timing and error capture. Returns True on success."""
    ctx.module = name
    rep = ctx.report.mod(name)
    t0 = time.time()
    ctx.log('start')
    try:
        fn(ctx)
        rep['status'] = 'ok'
        return True
    except Exception as e:  # noqa: BLE001 - one module failing must not stop the others / the validator
        rep['status'] = 'failed'
        ctx.error(f'unhandled {type(e).__name__}: {e}')
        ctx.error(traceback.format_exc())
        return False
    finally:
        rep['seconds'] = round(time.time() - t0, 2)
        ctx.log(f"{rep['status']} in {rep['seconds']}s")
        ctx.module = BUILD_OWNER
