"""xml1builder.resources - where the builder's own files are, from source or frozen (BUILDER_DESIGN.md 3.2).

Never open a file relative to a module's __file__ elsewhere in the builder: use data_path() / repo_root(). From source
the package lives in <repo>/tools/xml1builder; frozen (PyInstaller onedir) everything is under sys._MEIPASS
(`_internal/`): the package data as xml1builder/data/*, the pipeline's packaged research tables under research/
(phase 3 lays them out; xml1build reads them through $XML1_PORT_ROOT, set here before xml1build is imported)."""
from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
from pathlib import Path

PACKAGE = 'xml1builder'

# The research tables the pipeline reads in prepared mode (the builder's only mode) that no prepare stage makes: the
# frozen bundle carries them as research/<rel> (SPEC.md 27.13: traced over a full builder build - every file the
# builder opened under the repo). Everything else research-relative comes from the prepare stages (Sources overrides).
RESEARCH_DATA = (
    'characters/combat_compat.json',        # characters / heroes: unknown_handlers
    'scripts/verify/console_senders.json',  # scripts: the console-command senders
    'scripts/xml1_api.json',                # P3 + scripts: script-function tables (facts about the binaries)
    'scripts/xml2_api.json',
    'scripts/xml2fix_api.json',             # the xml2-fix script functions
    'scripts/xml2_console_cmds.txt',        # validate_frontend: console command names
    'sweep/graph.json',                     # the zone / mission graph - packaged without its text fields
    'sweep/zones.json',                     # media's sound-slot warning - packaged with the two fields it reads
)
# how tools/freeze_builder.py packages the tables that carry game text (BUILDER_DESIGN.md 5.2: a release holds none):
# graph.json loses every descname / description (scripts reads mission texts from the disc's mission plan instead,
# xml1build.scripts.PACKAGED_MARK); zones.json keeps zone -> {chr_characters, spawner_characters} (media.py).
PACKAGED_STRIP = {'sweep/graph.json': ('descname', 'description')}
PACKAGED_KEEP = {'sweep/zones.json': ('chr_characters', 'spawner_characters')}
PACKAGED_MARK = '_packaged'                 # = xml1build.scripts.PACKAGED_MARK


def frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def bundle_root() -> Path:
    """frozen: the unpacked bundle (sys._MEIPASS); from source: the repo's tools/ folder."""
    if frozen():
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def package_dir() -> Path:
    return bundle_root() / PACKAGE


def data_path(name: str) -> Path:
    return package_dir() / 'data' / name


def load_json(name: str, default=None):
    try:
        return json.loads(data_path(name).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def repo_root() -> Path:
    """the root the pipeline reads its packaged research tables from (xml1build.sources.REPO_ROOT)."""
    if frozen():
        return bundle_root()
    return Path(__file__).resolve().parents[2]


def setup() -> None:
    """make the pipeline importable (tools/ on sys.path) and point it at its data; call before importing xml1build.
    Frozen, $XML1_PORT_ROOT is always the bundle: a value inherited from a developer's shell must never send the
    frozen builder to a source tree's research tables (check_root() proves it after the pipeline is imported)."""
    tools = str(bundle_root())
    if tools not in sys.path:
        sys.path.insert(0, tools)
    if frozen():
        os.environ['XML1_PORT_ROOT'] = str(repo_root())


def check_root() -> None:
    """frozen: the pipeline's REPO_ROOT (xml1build.sources) must lie inside the bundle - else E_INTERNAL (the pipeline
    was imported before setup(), or $XML1_PORT_ROOT was changed underneath it)."""
    if not frozen():
        return
    from xml1build.sources import REPO_ROOT
    bundle = bundle_root().resolve()
    root = Path(REPO_ROOT).resolve()
    if root != bundle and bundle not in root.parents:
        from .errors import BuilderError
        raise BuilderError('E_INTERNAL', 'The builder is reading its data from outside its own folder.',
                           'Reinstall the builder.', {'data': str(root), 'bundle': str(bundle)})


@functools.lru_cache(maxsize=1)
def commit() -> str:
    """the source commit, 12 hex digits either way: data/build-info.json (written when freezing) or git (from
    source), else 'unknown'."""
    info = load_json('build-info.json', {}) or {}
    if info.get('commit'):
        return str(info['commit'])
    if frozen():
        return 'unknown'
    try:
        out = subprocess.run(['git', '-C', str(repo_root()), 'rev-parse', '--short=12', 'HEAD'], capture_output=True,
                             stdin=subprocess.DEVNULL, text=True, timeout=5,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return out.stdout.strip() or 'unknown'
    except (OSError, subprocess.SubprocessError):
        return 'unknown'
