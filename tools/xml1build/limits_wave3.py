"""xml1build.limits_wave3 - what the finished build demands of XML2 Fix's limits-wave-3 tables (builder side).

XMen2.exe keeps style events, FightMoves, effect files / definitions, primitive definitions, effect vectors and curves,
and its script nodes / values / compiled scripts in fixed pools. XML2 Fix's wave 3 raises them (`fix_ini.LIMITS_WAVE3`,
`--limits-wave3`); this module counts, from the finished <out> alone, how much of each a zone with an allowed four-hero
party loads, so the build fails when a table would overflow and warns when it is half full (the 2x rule).

The counting rules are limits-wave-3 DESIGN section 3 (the loader replay of the static report ffdb S1) and are binding:

  V-MOVES         every DIRECT <FightMove> child of every style file the zone and party register, shared_nodes included
                  (an inherited move copies an earlier move of the same style and allocates nothing beyond the child being
                  parsed); also the largest per-style count against the per-style move map (150, 0x500c60).
  V-EVENTS        a style's and the shared event templates load into the parser's temporary pools and are not resident; a
                  trigger instantiates its event. A move that inherits allocates a fresh copy of every inherited trigger
                  event (0x4f7e0c); a trigger whose tag matches an existing one modifies it and adds nothing; `reset`
                  frees what the move holds. Unresolvable triggers do not stay resident (reported). Final and transient
                  peak occupancy are separate numbers; the capacity applies to both.
  V-EFFECT-FILES  a new non-empty <Effect> file load = one definition + one file-table entry, keyed by the scope-qualified
                  name (`%i:%s`, 0x5647f0); DeathFxFile / IntervalFxFile effects load recursively; a scripted load counts
                  when the script names the effect literally (spawnEffect / spawnEffectBone).
  V-PRIMITIVES    an effect's direct children in order; a child counts when it has attributes AND a recognised primitive
                  type (`Sound` is none); admission per effect stops at PrimitivesPerEffect (extra children are reported),
                  globally at PrimitiveDefs.
  V-VECTORS       84 preset records are reserved; each accepted primitive requests 7 default vectors (they share presets); the
                  seven vector attributes parse six floats as (minimum, maximum - minimum); a vector reuses a preset only when
                  both three-component squared distances are below 0.001; equal non-preset vectors are NOT de-duplicated and
                  a replaced attribute does not free the previous vector.
  V-CURVES        the same model with 140 presets and the primitive's 14 curve attributes (effect-curves.md); plus the
                  combined effect-budget report that names the table that binds first.
  V-SCRIPTS       (validate_script.count_script) retained statement nodes = statements minus else / endif (temporaries,
                  allocated and freed again, 0x4da382) minus the lines the engine skips; one more temporary node is allowed
                  during compilation; values = literals + the largest distinct local set + one temporary; compiled scripts per
                  zone; capacity = [Limits] ScriptPools.

Every check covers each finished zone and every allowed four-hero party (the two special Professor X forms excluded; the
parties a forced mission seats, when the build knows them), and reports the count, the capacity (the value the build asks
the DLL for, or the game's own) and a witness zone and party. Above capacity is an error; equal to it, or above half of it,
is a warning. The self-test (`python -m xml1build.limits_wave3 --out <build>`) reproduces the static report's witnesses.

The scope of an effect load (the `%i` of the key) is chosen by whoever calls the loader, per resource owner; the model
treats every package load as one scope (the default) and reports the other extreme, every owning package its own scope, as
an upper bound. Neither is certified: the effect totals stay provisional until the pool diagnostics (D) have measured them.
"""
from __future__ import annotations

import collections
import itertools
import json
import re
import struct
from pathlib import Path

from . import actor_budget as AB
from . import combat_events as CE
from . import common as C
from . import fix_ini as FI
from . import style_budget as SB

# ------------------------------------------------------------------------------------------------ the tables
STOCK = {'FightStyles': 19, 'StyleEvents': 1064, 'FightMoves': 332, 'EffectTemplates': 220, 'PrimitiveDefs': 816,
         'EffectVectors': 710, 'PrimitivesPerEffect': 10, 'EffectCurves': 900, 'MoveTriggers': 19}
MOVES_PER_STYLE = 150                 # 0x500c60: each style's move map, node pop 0x500240 wraps at 0x96, unchecked
VECTOR_PRESETS = 84                   # reserved vector records (effect-curves.md twin: 0x416255 compares 84)
CURVE_PRESETS = 140                   # reserved curve records (0x416120, ids 0..139)
SCRIPT_STOCK = (620, 1556, 120, 30)   # statements 0x4d7e6e, values 0x4d6578, compiled scripts 0x4d86d1, contexts 0x4d8711
SCRIPT_X1 = (4096, 8192, 512, 128)
VALUE_TEMPORARIES = 1                 # allowance for the compiler's temporary return value (DESIGN section 3)
PARTY_SIZE = 4
EXCLUDED_HEROES = ('profxastral', 'profxgladiator')      # the two special Professor X forms are never a party member
WARN_FRACTION = 0.5                   # the 2x rule: warn above half of a capacity
VECTOR_EPS = 0.001
# the effect file reader's recognised primitive types (the table at 0x681ec0; `Sound` is not in it)
EFFECT_TYPES = frozenset('empty particlecloud sprite weathereffect orientedsprite spark line lightning cylinder model '
                         'floorcrack light ambientlight screenflash camerashake tesselatedmesh trail'.split())
# the seven vector attributes of the primitive reader 0x4172d0 and its fourteen curve attributes (in parse order)
VECTOR_ATTRS = ('transformrotation', 'origin', 'velocity', 'acceleration', 'origin2', 'velocity2', 'acceleration2')
CURVE_ATTRS = ('alpha', 'size', 'size2', 'length', 'width', 'offset', 'rotation', 'rotationradius', 'chaos',
               'attenuation', 'startarc', 'endarc', 'uvscroll', 'uvscale')
FX_REF_ATTRS = ('deathfxfile', 'intervalfxfile')
SCRIPT_EFFECT_CALLS = re.compile(r'spawnEffect(?:Bone)?\s*\(\s*[^,()]+,\s*[\'"]([^\'"]+)[\'"]', re.I)
# the metrics each rule reports: key -> (title, capacity key)
RULES = {
    'moves': 'FightMoves', 'events': 'StyleEvents', 'files': 'EffectTemplates', 'defs': 'EffectTemplates',
    'prims': 'PrimitiveDefs', 'vectors': 'EffectVectors', 'curves': 'EffectCurves',
}


def mode_of(v) -> str:
    """the --limits-wave3 level the build under validation was made with ('off' / 'on' / 'all')."""
    return str(getattr(getattr(getattr(v, 'ctx', v), 'args', None), 'limits_wave3', None) or 'off').lower()


def limits_for(mode='off', limits=None) -> dict:
    """the [Limits] section the build asks the DLL for (`limits` overrides)."""
    return dict(limits) if limits is not None else FI.limits_in_use(mode)


def capacity(name, limits=None) -> int:
    """a table's capacity: the DLL value the build asks for, else the game's own (a value below the game's own, or one
    that is no number, is the game's own: the DLL ignores it)."""
    stock = STOCK[name]
    value = (limits if limits is not None else FI.LIMITS).get(name)
    try:
        return max(int(str(value).strip()), stock) if value is not None else stock
    except ValueError:
        return stock


def script_capacity(limits=None):
    """(statements, values, compiled scripts, running contexts) for [Limits] ScriptPools (x1 = the wave-3 profile)."""
    value = str((limits if limits is not None else FI.LIMITS).get('ScriptPools', '')).strip().lower()
    return SCRIPT_X1 if value == 'x1' else SCRIPT_STOCK


def judge(count, cap):
    """'error' above the capacity, 'full' at it, 'half' above half of it, else None (DESIGN section 3: the 2x rule)."""
    if count > cap:
        return 'error'
    if count == cap:
        return 'full'
    if count > cap * WARN_FRACTION:
        return 'half'
    return None


# ------------------------------------------------------------------------------------------------ float helpers
def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def floats(text):
    """the floats of an attribute value (whitespace separated), or None when one is no number."""
    try:
        return [f32(float(t)) for t in str(text).split()]
    except (ValueError, OverflowError):
        return None


def vector_value(text):
    """a vector attribute -> (min x y z, max-min x y z) (six floats; fewer = no vector, more are ignored)."""
    vals = floats(text)
    if vals is None or len(vals) < 6:
        return None
    lo, hi = vals[:3], vals[3:6]
    return tuple(lo) + tuple(f32(hi[i] - lo[i]) for i in range(3))


def _dist2(a, b, lo, hi):
    return sum((a[i] - b[i]) ** 2 for i in range(lo, hi))


def matches_preset(value, presets, eps=VECTOR_EPS) -> bool:
    """a vector reuses a preset only when BOTH three-component squared distances are below eps."""
    return any(_dist2(value, p, 0, 3) < eps and _dist2(value, p, 3, 6) < eps for p in presets)


def curve_value(text):
    """a curve attribute -> eight floats (six given: the clamps default to 10000 / -10000), or None."""
    vals = floats(text)
    if vals is None or len(vals) < 6:
        return None
    vals = vals[:8]
    return tuple(vals + [10000.0, -10000.0][len(vals) - 6:]) if len(vals) < 8 else tuple(vals)


def curve_matches_preset(value, presets, eps=VECTOR_EPS) -> bool:
    """the vector rule on the curve's two coefficient triples, and its clamps equal within eps."""
    return any(_dist2(value, p, 0, 3) < eps and _dist2(value, p, 3, 6) < eps
               and abs(value[6] - p[6]) < eps and abs(value[7] - p[7]) < eps for p in presets)


# ------------------------------------------------------------------------------------------------ small tree helpers
def _lc(el):
    return {k.lower(): v for k, v in el.attrib.items()}


def _tag(el):
    return el.tag.lower() if isinstance(el.tag, str) else ''


PACKAGE_SCOPE = 0         # the scope the model gives every package-driven effect load (see the module docstring)


def effect_key(scope, name) -> str:
    """the effect file table's key, `%i:%s` (0x5647f0): a definition is found again only with the same scope."""
    return f'{scope}:{name}'


def effect_name(fn):
    """a package / reference effect file name -> the key under effects/ (lower case, no 'effects/' prefix, no .xmlb)."""
    n = C.norm(fn or '')
    if n.startswith('effects/'):
        n = n[len('effects/'):]
    return n[:-5] if n.endswith('.xmlb') else n


# ------------------------------------------------------------------------------------------------ style replay
class StyleInfo:
    """What one style file costs, replayed the way the loader 0x5010b0 reads it."""

    __slots__ = ('rel', 'present', 'moves', 'events', 'peak', 'largest_move_events', 'unresolved', 'trigger_cap')

    def __init__(self, rel):
        self.rel = rel
        self.present = False
        self.moves = 0                  # direct FightMove children
        self.events = 0                 # final resident trigger events
        self.peak = 0                   # transient peak while parsing (>= events)
        self.largest_move_events = 0
        self.unresolved = []            # [(move, trigger name)] triggers that stay dropped
        self.trigger_cap = 0

    def to_json(self):
        return {s: getattr(self, s) for s in self.__slots__}


def replay_style(root, shared, rel='', trigger_cap=None) -> StyleInfo:
    """Replay one style tree (a data/powerstyles, data/fightstyles or data/shared_nodes root).

    shared: combat_events.event_table() of data/shared_combat_events. trigger_cap: triggers a move may hold (the
    configured MoveTriggers; extra ones are freed, 0x4f6aa7)."""
    info = StyleInfo(rel)
    cap = capacity('MoveTriggers') if trigger_cap is None else trigger_cap
    info.trigger_cap = cap
    if root is None:
        return info
    info.present = True
    roots = list(root) if root.tag == 'xmlb_multiple_roots' else [root]
    style_events = {}
    for top in roots:
        for e in top:
            if _tag(e) == 'event':
                a = _lc(e)
                typ, _ = CE.resolve(a, style_events, shared)
                if typ is not None and a.get('name'):
                    style_events[a['name'].lower()] = (typ, a)
    moves = {}                          # move name -> [event dict] after the move (inheritable)
    live = 0                            # trigger events resident from the moves parsed so far
    peak = 0
    for top in roots:
        for m in top:
            if _tag(m) != 'fightmove':
                continue
            info.moves += 1
            ma = _lc(m)
            evs = [dict(x) for x in moves.get((ma.get('inherit') or ''), ())]
            # (the inherit key is the move name as written: Astra's replay keys the dict the same way)
            live_start = live
            live += len(evs)                                  # fresh copies of the inherited trigger events (0x4f7e0c)
            peak = max(peak, live)
            local = {}
            for e in m:
                if _tag(e) == 'event':
                    a = _lc(e)
                    typ, _ = CE.resolve(a, local, style_events, shared)
                    if typ is not None and a.get('name'):
                        local[a['name'].lower()] = (typ, a)
            for t in m:
                if _tag(t) != 'trigger':
                    continue
                z = _lc(t)
                if 'reset' in z:
                    live -= len(evs)
                    evs = []
                if not z.get('name') and 'tag' not in z:
                    continue
                if 'tag' in z:
                    tag = _tag_number(z['tag'])
                    match = next((x for x in evs if _tag_number(x.get('tag', 0)) == tag), None)
                    if match is not None:
                        match.update(z)                       # a matching tag modifies the trigger and adds nothing
                        continue
                    if not z.get('name'):
                        continue
                typ, _ = CE.resolve(z, local, style_events, shared)
                if typ is None:
                    info.unresolved.append((ma.get('name') or '', (z.get('name') or z.get('inherit') or '').lower()))
                    continue
                if len(evs) >= cap:
                    continue                                  # the move's trigger table is full: the event is freed
                evs.append(dict(z))
                live += 1
                peak = max(peak, live)
            # untagged triggers get a tag when the move ends (so a later inheritor's tag-only update can match them)
            mt = max([_tag_number(x.get('tag', 0)) for x in evs] + [0])
            for x in evs:
                if _tag_number(x.get('tag', 0)) == 0:
                    mt = (mt + 1) & 255
                    x['tag'] = str((255 - mt) & 255)
            moves[ma.get('name') or ''] = evs
            info.largest_move_events = max(info.largest_move_events, len(evs))
            live = live_start + len(evs)   # the inherited copies are the move's own events: only the move's final count stays
    info.events = live
    info.peak = max(peak, live)
    return info


def _tag_number(value):
    try:
        return int(value) & 255
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------------------------------------------ effect replay
class EffectInfo:
    __slots__ = ('name', 'ok', 'prims', 'vectors', 'curves', 'deps', 'extra', 'reason')

    def __init__(self, name):
        self.name = name
        self.ok = False                 # a successful non-empty <Effect> load
        self.prims = 0                  # accepted primitives
        self.vectors = 0                # non-preset vector requests
        self.curves = 0                 # non-preset curve requests
        self.deps = ()                  # DeathFxFile / IntervalFxFile effect names
        self.extra = 0                  # recognised children refused past PrimitivesPerEffect
        self.reason = ''                # why not ok: 'missing' / 'not an Effect' / 'empty'

    def to_json(self):
        return {s: getattr(self, s) for s in self.__slots__}


class Presets:
    """The default vectors and curve quads of effects/defaultvectors and effects/defaultquads (+ the zero preset)."""

    def __init__(self, vectors=(), curves=()):
        zero_v = (0.0,) * 6
        zero_c = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, f32(10000.0), f32(-10000.0))
        self.vectors = [v for v in vectors if v is not None] + [zero_v]
        self.curves = [c for c in curves if c is not None] + [zero_c]

    @classmethod
    def from_reader(cls, reader):
        vt = reader.tree('effects/defaultvectors')
        ct = reader.tree('effects/defaultquads')
        vecs = [vector_value(_lc(e).get('v', '')) for e in (vt if vt is not None else ())]
        cvs = [curve_value(_lc(e).get('q', '')) for e in (ct if ct is not None else ())]
        p = cls(vecs, cvs)
        p.found = (vt is not None, ct is not None)
        return p


def replay_effect(root, name, presets, per_effect, shared_presets=True) -> EffectInfo:
    """Replay one effect tree the way the effect reader 0x4172d0 / 0x418e00 loads it."""
    info = EffectInfo(name)
    if root is None:
        info.reason = 'missing'
        return info
    if _tag(root) != 'effect':
        info.reason = 'not an Effect'
        return info
    if len(root) == 0:
        info.reason = 'empty'
        return info
    info.ok = True
    deps = []
    for child in root:
        a = _lc(child)
        if not a or _tag(child) not in EFFECT_TYPES:
            continue                                  # needs attributes AND a recognised primitive type (Sound is none)
        if info.prims >= per_effect:
            info.extra += 1
            continue
        info.prims += 1
        for attr in VECTOR_ATTRS:
            if attr in a:
                val = vector_value(a[attr])
                if val is not None and not matches_preset(val, presets.vectors):
                    info.vectors += 1
        for attr in CURVE_ATTRS:
            if attr in a:
                val = curve_value(a[attr])
                if val is not None and not curve_matches_preset(val, presets.curves):
                    info.curves += 1
        for attr in FX_REF_ATTRS:
            if a.get(attr):
                deps.append(effect_name(a[attr]))
    info.deps = tuple(deps)
    return info


# ------------------------------------------------------------------------------------------------ party scan
def scan_parties(base, hero_sets, weights, *, size=PARTY_SIZE, score=None):
    """The worst allowed party for linear metrics over a union of resources.

    base: set of resources every party has; hero_sets: {hero: set of resources}; weights: {metric: {item: weight}} (a
    missing item weighs 0). Returns {'parties': n, 'max': {metric: (value, party)}, 'score': (best, party, {metric:
    value})}: the first party in name order wins a tie (only a strictly greater value replaces it). `score(values)` ranks
    parties for the combined report (None: no 'score')."""
    base = frozenset(base)
    metrics = list(weights)
    base_val = {m: sum(weights[m].get(x, 0) for x in base) for m in metrics}
    extras = {h: frozenset(s) - base for h, s in hero_sets.items()}
    names = sorted(extras)
    best = {m: (-1, ()) for m in metrics}
    best_score = (-1.0, (), {})
    n = 0
    for party in (itertools.combinations(names, min(size, len(names))) if names else [()]):
        n += 1
        union = frozenset().union(*(extras[h] for h in party)) if party else frozenset()
        vals = {m: base_val[m] + sum(weights[m].get(x, 0) for x in union) for m in metrics}
        for m in metrics:
            if vals[m] > best[m][0]:
                best[m] = (vals[m], party)
        if score is not None:
            sc = score(vals)
            if sc > best_score[0]:
                best_score = (sc, party, dict(vals))
    return {'parties': n, 'max': best, 'score': best_score if score is not None else None}


# ------------------------------------------------------------------------------------------------ the census
class Census:
    """The resources every finished zone and allowed party loads, replayed from a reader over <out>.

    reader: tree(rel_noext, exts=None) -> Element | None (actor_budget.OutReader / ValidatorReader, or a fixture);
    zones: the finished (converted) zone names; limits: the [Limits] section the build asks for (capacities);
    party_filter(zone, names) -> the heroes a zone's party may draw on (forced missions); read_text(rel) -> str | None
    reads <out>/<rel> (scripts); xml_refs: 'strict' (a `.xml` effect reference is looked up as written and is unresolved
    when no such file exists) or 'strip' (loaded as the .xmlb of the same name: the alternative reading)."""

    PERMANENT = AB.PERMANENT_PKGS

    def __init__(self, reader, zones, *, limits=None, party_filter=None, read_text=None, xml_refs='strict',
                 excluded=EXCLUDED_HEROES):
        self.r = reader
        self.zones = sorted(zones)
        self.limits = dict(limits) if limits is not None else dict(FI.LIMITS)
        self.party_filter = party_filter
        self.read_text = read_text
        self.xml_refs = xml_refs
        self.excluded = tuple(excluded)
        self._tree = {}
        self._pkg = {}
        self._style = {}
        self._effect = {}
        self._stats = None
        self._shared = None
        self._presets = None
        self._zone = {}

    # ---------------------------------------------------------------- inputs
    def tree(self, rel, exts=None):
        key = (rel, exts)
        if key not in self._tree:
            self._tree[key] = self.r.tree(rel, exts) if exts else self.r.tree(rel)
        return self._tree[key]

    def pkg(self, rel):
        """[(kind, normalized filename)] of a package (rel without extension)."""
        if rel not in self._pkg:
            t = self.tree(rel)
            self._pkg[rel] = [((e.tag or '').lower(), C.norm(e.get('filename') or '')) for e in t] if t is not None else []
        return self._pkg[rel]

    def stats(self):
        """({lower name: stats element}, [(hero name, skin)] of the playable heroes minus the excluded forms)."""
        if self._stats is None:
            by_name, heroes = {}, []
            for name in ('herostat', 'npcstat'):
                t = self.tree('data/' + name)
                for e in (t if t is not None else ()):
                    if _tag(e) == 'stats':
                        by_name.setdefault((e.get('name') or '').lower(), e)
            t = self.tree('data/herostat')
            for e in (t if t is not None else ()):
                n = (e.get('name') or '').lower()
                if _tag(e) == 'stats' and n and n != 'default' and (e.get('powerstyle') or '').strip() \
                        and (e.get('skin') or '').strip() and n not in self.excluded:
                    heroes.append((n, e.get('skin').strip()))
            self._stats = (by_name, heroes)
        return self._stats

    def shared_events(self):
        if self._shared is None:
            self._shared = CE.event_table(self.tree('data/shared_combat_events'))
        return self._shared

    def presets(self):
        if self._presets is None:
            self._presets = Presets.from_reader(self)
        return self._presets

    # ---------------------------------------------------------------- per file
    def style(self, rel) -> StyleInfo:
        if rel not in self._style:
            self._style[rel] = replay_style(self.tree(rel), self.shared_events(), rel,
                                            trigger_cap=capacity('MoveTriggers', self.limits))
        return self._style[rel]

    def effect(self, name) -> EffectInfo:
        if name not in self._effect:
            key = name[:-4] if self.xml_refs == 'strip' and name.endswith('.xml') else name
            self._effect[name] = replay_effect(self.tree('effects/' + key), name, self.presets(),
                                               capacity('PrimitivesPerEffect', self.limits))
        return self._effect[name]

    def closure(self, names):
        """the effect files a list of effect names loads: each name and, recursively, its Death / Interval effects."""
        out, todo = set(), list(names)
        while todo:
            x = todo.pop()
            if x in out:
                continue
            out.add(x)
            todo.extend(self.effect(x).deps)
        return frozenset(out)

    # ---------------------------------------------------------------- zone resources
    def character_pkg(self, name, skin, nc=False):
        return self.pkg(SB.CHARACTER_PKG.format(name=name, skin=skin, nc='_nc' if nc else '')[:-len('.pkgb')])

    def zone(self, z):
        """The zone's resources: {'entries', 'off', 'styles': (base, {hero: set}), 'effects': (base, {hero: set}),
        'scripts': [refs], 'scripted': [effect names], 'npcs': [names], 'owners': {...}}."""
        if z in self._zone:
            return self._zone[z]
        by_name, heroes = self.stats()
        hero_names = {n for n, _ in heroes} | set(self.excluded)
        perms = [e for p in self.PERMANENT for e in self.pkg(p)]
        ents = self.pkg('packages/generated/maps/' + z)
        chrb = self.tree('maps/' + z, ('.chrb',))
        npcs = sorted({(c.get('name') or '').lower() for c in (chrb.iter('character') if chrb is not None else ())} - {''})
        npc_entries = []
        for n in npcs:
            e = by_name.get(n)
            if e is None or n in hero_names:
                continue
            skin = (e.get('skin') or '').strip()
            if skin:
                npc_entries += self.character_pkg(n, skin)
        off = AB.combat_off(ents)
        base_entries = perms + ents + npc_entries

        def style_of(entries):
            return frozenset(fn for k, fn in entries if k == 'fightstyle' and fn)

        def effects_of(entries):
            return [effect_name(fn) for k, fn in entries if k == 'effect' and fn]

        hero_entries = {n: self.character_pkg(n, skin, off) for n, skin in heroes}
        # the scripts the zone loads: its package's scripts and the zone script (V7's zone residency set)
        world = self.tree('maps/' + z)
        node = C.find_world(world) if world is not None else None
        zs = ((node.get('zonescript') if node is not None else '') or '').strip()
        if not zs:
            zs = next(((el.get('zonescript') or '').strip() for el in (world.iter() if world is not None else ())
                       if (el.get('zonescript') or '').strip()), '')
        scripts = sorted({_script_ref(fn) for k, fn in ents if k == 'script' and fn} | ({_script_ref(zs)} if zs else set()))
        scripted = set()
        if self.read_text is not None:
            for ref in scripts:
                text = self.read_text(f'scripts/{ref}.py')
                if text:
                    scripted.update(effect_name(m) for m in SCRIPT_EFFECT_CALLS.findall(text))
        res = {
            'entries': ents, 'off': off, 'npcs': npcs, 'scripts': scripts, 'scripted': sorted(scripted),
            'styles': (style_of(base_entries), {n: style_of(e) for n, e in hero_entries.items()}),
            'effects': (self.closure(effects_of(base_entries) + sorted(scripted)),
                        {n: self.closure(effects_of(e)) for n, e in hero_entries.items()}),
            'owners': {'permanent': effects_of(perms), 'zone': effects_of(ents), 'npc': effects_of(npc_entries),
                       'heroes': {n: effects_of(e) for n, e in hero_entries.items()}},
        }
        self._zone[z] = res
        return res

    def heroes_for(self, z, sets):
        """the hero sets a zone's parties draw on (a forced mission seats fixed heroes)."""
        if self.party_filter is None:
            return sets
        names = list(self.party_filter(z, sorted(sets)) or sets)
        return {n: sets[n] for n in names if n in sets} or sets

    # ---------------------------------------------------------------- styles (V23 / V-MOVES / V-EVENTS)
    def style_weights(self, names):
        w = {'styles': {}, 'moves': {}, 'events': {}}
        for s in names:
            info = self.style(s)
            w['styles'][s] = 1
            w['moves'][s] = info.moves
            w['events'][s] = info.events
        return w

    def style_report(self):
        """{'zones': {zone: {'styles'|'moves'|'events'|'peak': (n, party)}}, 'largest_style': (moves, style)}."""
        if getattr(self, '_style_report', None) is not None:
            return self._style_report
        out = {}
        largest = (0, None)
        for z in self.zones:
            zr = self.zone(z)
            base, hero = zr['styles']
            hero = self.heroes_for(z, hero)
            names = set(base).union(*hero.values()) if hero else set(base)
            scan = scan_parties(base, hero, self.style_weights(names))
            row = {m: scan['max'][m] for m in ('styles', 'moves', 'events')}
            ev_party = row['events'][1]
            union = set(base).union(*(hero[h] for h in ev_party)) if ev_party else set(base)
            excess = max([self.style(s).peak - self.style(s).events for s in union] + [0])
            row['peak'] = (row['events'][0] + excess, ev_party)
            row['parties'] = scan['parties']
            out[z] = row
            for s in sorted(names):
                m = self.style(s).moves
                if m > largest[0]:
                    largest = (m, s)
        self._style_report = {'zones': out, 'largest_style': largest}
        return self._style_report

    # ---------------------------------------------------------------- effects (files / prims / vectors / curves)
    def effect_weights(self, names):
        w = {'files': {}, 'defs': {}, 'prims': {}, 'vectors': {}, 'curves': {}}
        for n in names:
            e = self.effect(n)
            if not e.ok:
                continue
            w['files'][n] = 1
            w['defs'][n] = 1
            w['prims'][n] = e.prims
            w['vectors'][n] = e.vectors
            w['curves'][n] = e.curves
        return w

    def effect_capacities(self):
        L = self.limits
        return {'files': capacity('EffectTemplates', L), 'defs': capacity('EffectTemplates', L),
                'prims': capacity('PrimitiveDefs', L), 'vectors': capacity('EffectVectors', L),
                'curves': capacity('EffectCurves', L)}

    def effect_report(self):
        """{zone: {'max': {metric: (total, party)}, 'budget': (utilisation, party, totals, binding)}}; vectors and curves
        include their reserved presets."""
        if getattr(self, '_effect_report', None) is not None:
            return self._effect_report
        caps = self.effect_capacities()
        reserved = {'vectors': VECTOR_PRESETS, 'curves': CURVE_PRESETS}
        out = {}

        def score(vals):
            return max((vals[m] + reserved.get(m, 0)) / caps[m] for m in caps)

        for z in self.zones:
            zr = self.zone(z)
            base, hero = zr['effects']
            hero = self.heroes_for(z, hero)
            names = set(base).union(*hero.values()) if hero else set(base)
            scan = scan_parties(base, hero, self.effect_weights(names), score=score)
            mx = {m: (scan['max'][m][0] + reserved.get(m, 0), scan['max'][m][1]) for m in caps}
            s, party, vals = scan['score']
            totals = {m: vals[m] + reserved.get(m, 0) for m in caps}
            binding = max(caps, key=lambda m: totals[m] / caps[m])
            out[z] = {'max': mx, 'budget': (s, party, totals, binding), 'parties': scan['parties']}
        self._effect_report = out
        return out

    def effect_problems(self):
        """effects the zones' packages (or other effects) name that cannot load: {name: 'reason; first named by ...'}."""
        out = {}
        for z in self.zones:
            base, hero = self.zone(z)['effects']
            for n in sorted(set(base).union(*hero.values()) if hero else set(base)):
                e = self.effect(n)
                if not e.ok and n not in out:
                    by = next((o for o, oe in sorted(self._effect.items()) if n in oe.deps), None)
                    out[n] = f'{e.reason}; named by ' + (f'the Death/Interval effect of {by}' if by else f'a package of {z}')
        return out

    def scoped_files(self, z, party):
        """The upper bound of the scope question: every owning package its own scope (permanent / zone / NPC / each hero),
        so one effect loaded by two owners counts twice. Returns (files, set of `scope:name` keys)."""
        zr = self.zone(z)
        own = zr['owners']
        keys = set()
        for owner, names in (('permanent', own['permanent']), ('zone', own['zone']), ('npc', own['npc']),
                             ('script', zr['scripted'])):
            keys |= {effect_key(owner, n) for n in self.closure(names)}
        for h in party:
            keys |= {effect_key(h, n) for n in self.closure(own['heroes'].get(h, ()))}
        keys = {k for k in keys if self.effect(k.split(':', 1)[1]).ok}
        return len(keys), keys

    # ---------------------------------------------------------------- scripts
    def script_report(self, count_script):
        """{zone: {...}} per zone from the raw script texts (count_script: validate_script.count_script)."""
        out = {}
        for z in self.zones:
            zr = self.zone(z)
            n = lit = loc = tmp = skp = src = present = 0
            for ref in zr['scripts']:
                text = self.read_text(f'scripts/{ref}.py') if self.read_text is not None else None
                if text is None:
                    continue
                present += 1
                r = count_script(text)
                src += r.statements
                tmp += r.temporaries
                skp += r.skipped
                n += r.retained
                lit += r.literals
                loc = max(loc, len(r.locals))
            out[z] = {'scripts': present, 'source_statements': src, 'temporaries': tmp, 'skipped': skp, 'retained': n,
                      'literals': lit, 'locals': loc, 'values': lit + loc + VALUE_TEMPORARIES, 'refs': len(zr['scripts'])}
        return out


def _script_ref(value):
    """a script attribute value -> the reference under scripts/ (no extension, forward slashes, lower case)."""
    s = C.norm(value or '')
    if s.startswith('scripts/'):
        s = s[len('scripts/'):]
    return s[:-3] if s.endswith('.py') else s


# ------------------------------------------------------------------------------------------------ the checks
def _party_text(party):
    return ', '.join(party) if party else '(no party)'


def _rate(ck, label, rows, cap, what, hint):
    """Judge one table: rows = {zone: (count, party)}; an error for every zone above the capacity, a warning (the worst
    zone only) at equality or above half of it; the witness is recorded in ck.counts / ck.details."""
    zones = sorted(rows)
    over = [z for z in zones if rows[z][0] > cap]
    worst = max(zones, key=lambda z: (rows[z][0], -zones.index(z))) if zones else None
    ck.set('capacity', cap)
    ck.set('zones_checked', len(zones))
    if worst is None:
        return
    count, party = rows[worst]
    ck.set(f'max_{label}', count)
    ck.set('witness_zone', worst)
    ck.set('witness_party', _party_text(party))
    ck.details['witness'] = {'zone': worst, 'party': list(party), label: count, 'capacity': cap}
    ck.set('zones_over_capacity', len(over))
    ck.set('zones_above_half', sum(1 for z in zones if judge(rows[z][0], cap) in ('half', 'full')))
    for z in over:
        c, p = rows[z]
        ck.error(f'{z}: {c} {what} with the party {_party_text(p)} (> {cap}); {hint}')
    verdict = judge(count, cap)
    if verdict == 'full':
        ck.warn(f'{worst}: {count} {what} with the party {_party_text(party)}: the table ({cap}) is full, with no room '
                f'for a load the replay does not model; {hint}')
    elif verdict == 'half':
        ck.warn(f'{worst}: {count} {what} with the party {_party_text(party)}: above half of the table ({cap}); {hint}')
    ck.details['zones'] = {z: [rows[z][0], list(rows[z][1])] for z in zones}


def check_moves(c: Census, ck):
    """V-MOVES: FightMoves per zone and party against the pool, and the largest per-style count against 150."""
    rep = c.style_report()
    cap = capacity('FightMoves', c.limits)
    _rate(ck, 'moves', {z: r['moves'] for z, r in rep['zones'].items()}, cap, 'FightMoves',
          'a move past the pool corrupts a live one (0x500de0); the raised pool\'s guard refuses it')
    n, style = rep['largest_style']
    ck.set('per_style_capacity', MOVES_PER_STYLE)
    ck.set('max_moves_in_one_style', n)
    ck.set('largest_style', style)
    ck.details['largest_style'] = {'style': style, 'moves': n, 'capacity': MOVES_PER_STYLE}
    verdict = judge(n, MOVES_PER_STYLE)
    msg = f'{style}: {n} FightMoves in one style against the per-style move map ({MOVES_PER_STYLE}, 0x500c60, unchecked)'
    if verdict == 'error':
        ck.error(msg)
    elif verdict == 'full':
        ck.warn(msg + ': full')
    elif verdict == 'half':
        ck.warn(msg + ': above half')
    else:
        ck.note(msg)


def check_events(c: Census, ck):
    """V-EVENTS: resident style events (final, and the transient peak) per zone and party."""
    rep = c.style_report()
    cap = capacity('StyleEvents', c.limits)
    hint = 'a refused event drops its trigger (the style event pool, 0x4faeb9)'
    _rate(ck, 'events', {z: r['events'] for z, r in rep['zones'].items()}, cap, 'resident style events (final)', hint)
    peaks = {z: r['peak'] for z, r in rep['zones'].items()}
    zp = max(sorted(peaks), key=lambda z: peaks[z][0]) if peaks else None
    if zp:
        ck.set('max_events_transient_peak', peaks[zp][0])
        ck.details['transient_peak'] = {'zone': zp, 'party': list(peaks[zp][1]), 'events': peaks[zp][0], 'capacity': cap}
        if peaks[zp][0] > cap:
            ck.error(f'{zp}: transient peak {peaks[zp][0]} style events with the party {_party_text(peaks[zp][1])} '
                     f'(> {cap}); {hint}')
    unresolved = {rel: info.unresolved for rel, info in sorted(c._style.items()) if info.unresolved}
    ck.set('styles_with_unresolved_triggers', len(unresolved))
    ck.details['unresolved_triggers'] = {rel: [list(t) for t in rows] for rel, rows in unresolved.items()}
    for rel, rows in unresolved.items():
        ck.note(f'{rel}: {len(rows)} trigger(s) name no resolvable event and stay dropped (not counted): {rows[:4]}')


EFFECT_LABELS = {'files': 'effect files', 'defs': 'effect definitions', 'prims': 'primitive definitions',
                 'vectors': 'effect vectors', 'curves': 'effect curves'}


def _effect_check(c: Census, ck, metric, cap, hint):
    rep = c.effect_report()
    _rate(ck, metric, {z: r['max'][metric] for z, r in rep.items()}, cap, EFFECT_LABELS[metric], hint)
    problems = c.effect_problems()
    ck.set('unresolved_effect_references', len(problems))
    ck.details['unresolved_effects'] = dict(sorted(problems.items()))
    for name, why in sorted(problems.items())[:20]:
        ck.note(f'effect {name}: {why} (no loadable file; the load is refused and not counted)')
    return rep


def check_effect_files(c: Census, ck):
    """V-EFFECT-FILES: distinct (scope, name) effect loads per zone and party against the file / definition tables."""
    cap = capacity('EffectTemplates', c.limits)
    rep = _effect_check(c, ck, 'files', cap, 'the effect past the table is refused and never draws (0x4194e4 / 0x418d90)')
    ck.set('scope_model', 'package: every package load shares one scope')
    w = ck.details.get('witness')
    if w:
        n, _ = c.scoped_files(w['zone'], w['party'])
        ck.set('files_if_every_owner_is_a_scope', n)
        ck.details['scope_upper_bound'] = {'zone': w['zone'], 'party': w['party'], 'files': n}
        if n > cap:
            ck.warn(f"{w['zone']}: {n} effect files if every owning package is its own scope (> {cap}): the scope of a "
                    f"load is the caller's and is not modelled; the pool diagnostics measure it")
    return rep


def check_primitives(c: Census, ck):
    """V-PRIMITIVES: accepted primitive definitions per zone and party, and the children past the per-effect cap."""
    cap = capacity('PrimitiveDefs', c.limits)
    rep = _effect_check(c, ck, 'prims', cap, 'the primitive is omitted: the effect misses a sprite, trail or cloud')
    per = capacity('PrimitivesPerEffect', c.limits)
    ck.set('per_effect_capacity', per)
    over = sorted((e.extra, n) for n, e in c._effect.items() if e.extra)
    biggest = max(((e.prims, n) for n, e in sorted(c._effect.items()) if e.ok), default=(0, None))
    ck.set('max_primitives_in_one_effect', biggest[0])
    ck.set('largest_effect', biggest[1])
    ck.set('effects_with_refused_children', len(over))
    ck.details['effects_over_per_effect_cap'] = {n: x for x, n in over}
    for x, n in over[:20]:
        ck.error(f'effect {n}: {x} recognised primitive(s) past PrimitivesPerEffect={per} (the extra children are refused)')
    verdict = judge(biggest[0], per)
    if biggest[1] and verdict in ('full', 'half'):
        ck.warn(f'effect {biggest[1]}: {biggest[0]} primitives against PrimitivesPerEffect={per}'
                + (' (full)' if verdict == 'full' else ' (above half)'))
    return rep


def check_vectors(c: Census, ck):
    """V-VECTORS: preset records (84) + every non-preset vector request."""
    cap = capacity('EffectVectors', c.limits)
    ck.set('presets_reserved', VECTOR_PRESETS)
    ck.set('presets_found', len(c.presets().vectors))
    return _effect_check(c, ck, 'vectors', cap, "a vector past the pool is the zero vector: the primitive's motion or "
                                                 "offset flattens (0x416255)")


def check_curves(c: Census, ck):
    """V-CURVES: preset records (140) + every non-preset curve request, and the combined effect budget."""
    cap = capacity('EffectCurves', c.limits)
    ck.set('presets_reserved', CURVE_PRESETS)
    ck.set('presets_found', len(c.presets().curves))
    rep = _effect_check(c, ck, 'curves', cap, 'a curve past the pool is flat zero: the effect loses its size or alpha '
                                               '(0x416120)')
    caps = c.effect_capacities()
    worst = None
    for z in sorted(rep):
        u, party, totals, binding = rep[z]['budget']
        if worst is None or u > worst[0]:
            worst = (u, z, party, totals, binding)
        if u > 1.0:
            ck.error(f'{z}: effect budget over: ' + ', '.join(f'{EFFECT_LABELS[m]} {totals[m]}/{caps[m]}' for m in caps)
                     + f' with the party {_party_text(party)}; {EFFECT_LABELS[binding]} binds first')
    if worst:
        u, z, party, totals, binding = worst
        budget = {m: {'count': totals[m], 'capacity': caps[m], 'utilisation': round(totals[m] / caps[m], 4)} for m in caps}
        ck.details['effect_budget'] = {'zone': z, 'party': list(party), 'binding': binding, 'tables': budget}
        ck.set('effect_budget_binding', binding)
        ck.set('effect_budget_zone', z)
        ck.set('effect_budget_utilisation', round(u, 4))
        line = ', '.join(f'{EFFECT_LABELS[m]} {totals[m]}/{caps[m]}' for m in caps)
        ck.note(f'effect budget at {z} with {_party_text(party)}: {line}; {EFFECT_LABELS[binding]} binds first ({u:.0%})')
        if WARN_FRACTION < u <= 1.0:
            ck.warn(f'{z}: effect budget {u:.0%} full ({EFFECT_LABELS[binding]} binds first: {totals[binding]}/'
                    f'{caps[binding]}) with the party {_party_text(party)}')
    ck.details['effect_budget_by_zone'] = {z: {'utilisation': round(r['budget'][0], 4), 'binding': r['budget'][3],
                                               'party': list(r['budget'][1])} for z, r in rep.items()}
    return rep


class _Sub:
    def __init__(self):
        self.counts, self.details, self.errors, self.warnings = {}, {}, [], []

    def set(self, k, v):
        self.counts[k] = v

    def error(self, m):
        self.errors.append(m)

    def warn(self, m):
        self.warnings.append(m)


def check_scripts(c: Census, ck, count_script):
    """V-SCRIPTS: retained statement nodes, values and compiled scripts per zone against ScriptPools."""
    nodes_cap, values_cap, scripts_cap, contexts_cap = script_capacity(c.limits)
    rep = c.script_report(count_script)
    ck.set('statements_capacity', nodes_cap)
    ck.set('values_capacity', values_cap)
    ck.set('scripts_capacity', scripts_cap)
    ck.set('contexts_capacity', contexts_cap)
    ck.set('zones_checked', len(rep))
    ck.details['zones'] = rep
    ck.note(f'running contexts ({contexts_cap}) cannot be measured statically: the pool diagnostics (D) count them')
    for key, cap, what, hint in (
            ('retained', nodes_cap, 'statement nodes (retained, plus the compile-time temporary)',
             'a full pool skips every later line, control directives included (0x4d7e6e / 0x4d979c)'),
            ('values', values_cap, 'script values', 'an exhausted value pool crashes the compiler (0x4d89f1)'),
            ('scripts', scripts_cap, 'compiled scripts', 'the script object pool (0x4d86d1)')):
        # one more temporary node is allowed during compilation (else / endif take one and free it again)
        rows = {z: (r[key] + (1 if key == 'retained' else 0), ()) for z, r in rep.items()}
        sub = _Sub()
        _rate(sub, key, rows, cap, what, hint)
        ck.counts.update({f'{key}_{k}': val for k, val in sub.counts.items() if k != 'capacity' and k != 'zones_checked'})
        ck.errors += [m.replace(' with the party (no party)', '') for m in sub.errors]
        ck.warnings += [m.replace(' with the party (no party)', '') for m in sub.warnings]
        w = sub.details.get('witness')
        if w:
            ck.details[f'witness_{key}'] = {'zone': w['zone'], key: w[key], 'capacity': cap}
    if rep:
        top = max(sorted(rep), key=lambda z: rep[z]['retained'])
        r = rep[top]
        ck.set('max_retained_nodes', r['retained'])
        ck.set('max_retained_zone', top)
        ck.note(f"largest zone script load: {top} with {r['retained']} retained statement nodes ({r['source_statements']} "
                f"source statements, {r['temporaries']} else/endif temporaries, {r['skipped']} skipped lines), "
                f"{r['values']} values, {r['scripts']} compiled scripts")


# ------------------------------------------------------------------------------------------------ the validator hooks
def census_for(v):
    """the Census of a validate.Validator (cached on it): its reader, V7's zone set, the build's forced parties."""
    if getattr(v, '_w3_census', None) is None:
        from . import talent_budget as TB

        def party_filter(zone, names):
            try:
                kept, _ = TB.mission_parties(v.ctx, zone, {n: set() for n in names})
                return sorted(kept)
            except Exception:                 # noqa: BLE001 - no forced-party plan: every party is allowed
                return names

        def read_text(rel):
            try:
                return v.read(rel).decode('latin-1')
            except Exception:                 # noqa: BLE001
                return None

        v._w3_census = Census(AB.ValidatorReader(v), v.converted_zones(), limits=limits_for(mode_of(v)),
                              party_filter=party_filter, read_text=read_text)
    return v._w3_census


def enabled(v) -> bool:
    """the wave-3 validators run only for a build made with --limits-wave3 (the default build's report is unchanged)."""
    return mode_of(v) != 'off'


def run_check(v, ck, fn):
    """one wave-3 check against the validator's census."""
    if not enabled(v):
        ck.status = 'skipped'
        ck.note('limits wave 3 is off for this build (--limits-wave3 off): not checked')
        return
    ck.set('limits_wave3', mode_of(v))
    fn(census_for(v), ck)


def validate_scripts(v, ck):
    from . import validate_script as VS
    run_check(v, ck, lambda c, k: check_scripts(c, k, VS.count_script))


VALIDATORS = (
    ('V-MOVES', 'FightMoves per zone and style', lambda v, ck: run_check(v, ck, check_moves)),
    ('V-EVENTS', 'style events', lambda v, ck: run_check(v, ck, check_events)),
    ('V-EFFECT-FILES', 'effect files and definitions', lambda v, ck: run_check(v, ck, check_effect_files)),
    ('V-PRIMITIVES', 'primitive definitions', lambda v, ck: run_check(v, ck, check_primitives)),
    ('V-VECTORS', 'effect vectors', lambda v, ck: run_check(v, ck, check_vectors)),
    ('V-CURVES', 'effect curves and the combined effect budget', lambda v, ck: run_check(v, ck, check_curves)),
    ('V-SCRIPTS', 'script pools', validate_scripts),
)


# ------------------------------------------------------------------------------------------------ the self-test
# the static report's replay maxima (limits wave 3 DESIGN revision 2, ffdb S1) a finished 080c-era build reproduces
EXPECTED_WITNESSES = (
    ('styles', 24, 'sewers/grso/sewers3_1_3', 'distinct style files'),
    ('moves', 306, 'astral/ast3/astral3_4', 'FightMoves in one zone'),
    ('largest style', 108, 'data/shared_nodes', 'FightMoves in one style (against 150)'),
    ('events', 831, 'astroid_m/visit1/asteroid2_1', 'resident style events (LIKELY)'),
    ('mastermold2 nodes', 585, 'mastermold/mastermold2', 'retained script statement nodes, 27 scripts (622 source lines)'),
)
PROVISIONAL_EFFECTS = (('files', 207), ('prims', 627), ('vectors', 647))      # at mastermold/mastermold2 (provisional)


def converted_zones_of(out):
    """the zones the build converted: _build/zones_detail.json 'converted'."""
    p = Path(out) / '_build' / 'zones_detail.json'
    doc = json.loads(p.read_text(encoding='utf-8'))
    conv = doc.get('converted')
    if isinstance(conv, dict):
        conv = list(conv)
    return sorted(C.norm(z) for z in conv)


def census_for_out(out, *, limits=None, xml_refs='strict'):
    """A Census over an existing build folder (read-only)."""
    out = Path(out)
    reader = AB.OutReader(str(out))

    def read_text(rel):
        p = reader.index().get(C.norm(rel))
        return Path(p).read_bytes().decode('latin-1') if p else None

    return Census(reader, converted_zones_of(out), limits=limits, read_text=read_text, xml_refs=xml_refs)


def witness_table(c: Census, count_script):
    """Replay everything and return ({row: (value, witness)}, the census) for the self-test and the report."""
    sr = c.style_report()
    zones = sr['zones']

    def best(key):
        z = max(sorted(zones), key=lambda zz: zones[zz][key][0])
        return zones[z][key][0], z, zones[z][key][1]

    rows = {}
    n, z, party = best('styles')
    rows['styles'] = (n, z, party)
    n, z, party = best('moves')
    rows['moves'] = (n, z, party)
    n, z, party = best('events')
    rows['events'] = (n, z, party)
    rows['largest style'] = (sr['largest_style'][0], sr['largest_style'][1], ())
    scripts = c.script_report(count_script)
    top = max(sorted(scripts), key=lambda zz: scripts[zz]['retained'])
    rows['retained nodes (largest zone)'] = (scripts[top]['retained'], top, ())
    mm = scripts.get('mastermold/mastermold2')
    if mm is not None:
        rows['mastermold2 nodes'] = (mm['retained'], 'mastermold/mastermold2', ())
    return rows, scripts


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='replay the limits-wave-3 counting rules over a finished build (read-only)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--mode', choices=('off', 'on', 'all'), default='on', help='capacities: the level the build asks for')
    ap.add_argument('--xml-refs', choices=('strict', 'strip'), default='strict')
    ap.add_argument('--json', help='write the full report here')
    a = ap.parse_args(argv)
    from . import validate_script as VS
    c = census_for_out(a.out, limits=limits_for(a.mode), xml_refs=a.xml_refs)
    rows, scripts = witness_table(c, VS.count_script)
    bad = 0
    print(f'{"row":<16}{"value":>7}  {"expected":>8}  witness')
    extra = rows.get('retained nodes (largest zone)')
    for name, want, zone, what in EXPECTED_WITNESSES:
        got, z, party = rows.get(name, (None, None, ()))
        ok = got == want and z == zone
        bad += not ok
        print(f'{name:<16}{got:>7}  {want:>8}  {z}{" / " + ", ".join(party) if party else ""}  [{"ok" if ok else "DIFFERS"}] {what}')
    if extra:
        print(f'{"largest zone":<16}{extra[0]:>7}  {"":>8}  {extra[1]}  [info] retained script nodes (the corrected count is not largest at MM2)')
    mm = 'mastermold/mastermold2'
    if mm in c.zones:
        rep = c.effect_report()[mm]
        party = rep['budget'][1]
        print(f'\n{mm} effects (party {", ".join(party)}; provisional in the design):')
        for m, want in PROVISIONAL_EFFECTS:
            print(f'  {EFFECT_LABELS[m]:<24}{rep["max"][m][0]:>6}  (design ~{want})')
        n, _ = c.scoped_files(mm, party)
        print(f'  effect files if every owner is a scope: {n}')
        print('  unresolved effect references:', dict(sorted(c.effect_problems().items())))
        print('  budget:', {m: (rep['budget'][2][m], c.effect_capacities()[m]) for m in c.effect_capacities()},
              'binds first:', rep['budget'][3])
        print('  scripts:', scripts[mm])
    if a.json:
        Path(a.json).write_text(json.dumps({'witnesses': {k: [v[0], v[1], list(v[2])] for k, v in rows.items()},
                                            'scripts': scripts}, indent=1, sort_keys=True), encoding='utf-8')
    return 1 if bad else 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
