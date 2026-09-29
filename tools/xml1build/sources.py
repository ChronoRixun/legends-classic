"""xml1build.sources - where every input of a build lives (BUILDER_DESIGN.md 1.4 / 1.5 / F6; SPEC.md section 27).

A `Sources` object is handed to BuildContext (ctx.sources) and replaces the module constants the pipeline used to
read directly (common.ROOT / X1_LOOSE / X1_ASSETS / X1_XBOX / RESEARCH / DEFAULT_BASE):

  x1_loose   the unpacked .fb bundles + _fb_manifest.json          (ctx.x1_loose, ctx.x1_loose_index, ctx.manifest)
  x1_assets  assetsfb.zip unzipped (data tables, textures, ...)     (ctx.x1_assets, ctx.x1_assets_index)
  x1_xbox    disc files: default.xbe, sounds/zsds, movies/ntsc      (ctx.x1_xbox)
  xml2       the XML2 PC install (the base the output copies)       (ctx.base)
  research   the research tree: tracked tables (API tables, graph.json, ...) and, in developer mode, the gitignored
             research outputs (scripts/out, sound/out, sound/music0x20)
  overrides  research-relative paths served from somewhere else: `research_path(rel)` maps 'scripts/mission_plan.json'
             to a prepared table, 'scripts/out/...' to a prepared stage output, ... (longest matching prefix wins)
  collisions the characters/collisions.json x1names reads (every x1_ rename), = research_path of that rel
  movies_index  prepared mode: P1's movies.json (the NTSC movies' names, sizes and headers), which the movie
             providers read when the disc was prepared without the movie files (--no-movies; media.x1_movie_files)

Two modes:
  developer  today's folders: <repo>/xml1_loose, xml1_assets, xml1_xbox, research/ (no overrides) and --base.
             build_xml1.py without --sources is this mode and builds exactly what it built before (proven file for
             file, tools/build_equiv.py).
  prepared   the prepare stages' cache (tools/xml1build/prepare): P1 `disc` (the XML1 trees read from the disc
             image), P2 `tables` (research tables regenerated from P1 + the XML2 install), P3 `scripts`
             (scripts/out), P4 `sound` (sound/out) and P5 `music` (sound/music0x20). Only the tracked research
             tables no stage makes (API tables, graph.json, x1_namespace_map.json, ...: packaged data) still come
             from research/.

Every path here is read-only for the build: common._check_out_safe refuses an <out> that overlaps any of them."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# the repo: tools/, research/ (packaged code + data). $XML1_PORT_ROOT overrides it: a frozen builder (PyInstaller,
# BUILDER_DESIGN.md 3.2) sets it to the folder its packaged research tables unpack to, before importing xml1build.
REPO_ROOT = Path(os.environ.get('XML1_PORT_ROOT') or Path(__file__).resolve().parents[2]).resolve()


def _local_path(env, key, default):
    """A developer path: $env, else `key` in the untracked local_paths.json at the repo root (tools/local_paths.py
    documents it), else `default`. A frozen builder has no such file and always gets --xml2 explicitly."""
    if os.environ.get(env):
        return os.environ[env]
    try:
        with open(REPO_ROOT / 'local_paths.json', encoding='utf-8') as f:
            value = json.load(f).get(key)
        if value:
            return value
    except (OSError, ValueError, AttributeError):
        pass
    return default


DEFAULT_XML2 = Path(_local_path('XML2_DIR', 'xml2_dir', 'X-Men Legends II'))   # developer default for --base

MODES = ('developer', 'prepared')

# research-relative inputs P2 `tables` regenerates (prepare/tables.py OUTPUTS maps them to its files)
TABLE_RELS = ('scripts/mission_plan.json', 'characters/collisions.json', 'characters/x2_stats_refs.json',
              'sound/names_xml1.json')
COLLISIONS_REL = 'characters/collisions.json'


def _rel(rel) -> str:
    return str(rel).replace('\\', '/').strip('/')


@dataclass(frozen=True)
class Sources:
    mode: str
    root: Path
    research: Path
    x1_loose: Path
    x1_assets: Path
    x1_xbox: Path
    xml2: Path
    cache: Path | None = None
    overrides: tuple = ()                 # ((research-relative prefix, absolute Path), ...)
    stages: dict = field(default_factory=dict, compare=False, hash=False)   # provenance: stage -> stage.json
    movies_index: Path | None = None      # prepared mode: P1's movies.json

    # ------------------------------------------------------------------ constructors
    @classmethod
    def developer(cls, xml2=DEFAULT_XML2, root=REPO_ROOT) -> 'Sources':
        """today's folders (the repo's gitignored xml1_* trees and research/)."""
        root = Path(root).resolve()
        return cls('developer', root, root / 'research', root / 'xml1_loose', root / 'xml1_assets',
                   root / 'xml1_xbox', Path(xml2).resolve())

    @classmethod
    def prepared(cls, disc_dir, xml2, tables_dir=None, cache=None, root=REPO_ROOT, stages=None,
                 overrides=None) -> 'Sources':
        """the prepare stages' outputs: disc_dir = P1's directory (loose/, assets/, xbox/), tables_dir = P2's (its
        OUTPUTS rels are overridden); research/ for everything else. `overrides` adds {research rel: path}."""
        from .prepare import disc as P1           # local import: the pipeline imports sources without prepare
        root = Path(root).resolve()
        d = Path(disc_dir).resolve()
        ov = {}
        if tables_dir is not None:
            from .prepare import tables as P2
            for rel, name in P2.OUTPUTS.items():
                ov[rel] = Path(tables_dir).resolve() / name
        ov.update({_rel(k): Path(v).resolve() for k, v in (overrides or {}).items()})
        mi = d / P1.MOVIES_JSON
        return cls('prepared', root, root / 'research', d / P1.LOOSE, d / P1.ASSETS, d / P1.XBOX,
                   Path(xml2).resolve(), Path(cache).resolve() if cache else None,
                   tuple(sorted(ov.items())), dict(stages or {}), mi if mi.is_file() else None)

    # ------------------------------------------------------------------ lookups
    def research_path(self, rel) -> Path:
        """where the research input `rel` ('scripts/out/zone_acts.json', 'sound/out/all_ima/eng', ...) lives: an
        override (longest matching prefix, whole path components) or research/<rel>."""
        r = _rel(rel)
        best = None
        for k, p in self.overrides:
            if (r == k or r.startswith(k + '/')) and (best is None or len(k) > len(best[0])):
                best = (k, p)
        if best is None:
            return self.research / r
        k, p = best
        return p / r[len(k) + 1:] if r != k else p

    @property
    def collisions(self) -> Path:
        return self.research_path(COLLISIONS_REL)

    def protected(self) -> tuple:
        """trees <out> may never overlap (inputs, the repo's code and data, the cache)."""
        t = [self.x1_loose, self.x1_assets, self.x1_xbox, self.research, self.root / 'tools']
        t += [p for _, p in self.overrides]
        if self.cache is not None:
            t.append(self.cache)
        return tuple(t)

    def describe(self) -> dict:
        """JSON-able summary (build_xml1.py writes it to <out>/_build/sources.json in prepared mode)."""
        return {'mode': self.mode, 'root': self.root.as_posix(), 'research': self.research.as_posix(),
                'x1_loose': self.x1_loose.as_posix(), 'x1_assets': self.x1_assets.as_posix(),
                'x1_xbox': self.x1_xbox.as_posix(), 'xml2': self.xml2.as_posix(),
                'cache': self.cache.as_posix() if self.cache else None,
                'overrides': {k: p.as_posix() for k, p in self.overrides}, 'stages': self.stages,
                'movies_index': self.movies_index.as_posix() if self.movies_index else None}

    @classmethod
    def from_json(cls, d: dict) -> 'Sources':
        return cls(d['mode'], Path(d['root']), Path(d['research']), Path(d['x1_loose']), Path(d['x1_assets']),
                   Path(d['x1_xbox']), Path(d['xml2']), Path(d['cache']) if d.get('cache') else None,
                   tuple(sorted((k, Path(v)) for k, v in (d.get('overrides') or {}).items())),
                   dict(d.get('stages') or {}), Path(d['movies_index']) if d.get('movies_index') else None)

    @classmethod
    def for_out(cls, out, xml2=None) -> 'Sources':
        """the Sources a build in <out> was made with: <out>/_build/sources.json (prepared builds) or developer
        mode (standalone checks and self-tests over an existing build)."""
        p = Path(out) / '_build' / 'sources.json'
        try:
            return cls.from_json(json.loads(p.read_text(encoding='utf-8')))
        except (OSError, ValueError, KeyError, TypeError):
            return cls.developer(xml2 or DEFAULT_XML2)


def apply_collisions(sources: Sources):
    """point xml1build.lib.x1names (every map_* rename) at the sources' collisions.json. x1names reads the file
    lazily and caches it per process; this resets that cache when the path changes."""
    from .lib import x1names
    x1names.use_collisions(str(sources.collisions))
