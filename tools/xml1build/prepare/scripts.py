"""xml1build.prepare.scripts - prepare stage P3 `scripts` (BUILDER_DESIGN.md 1.5; SPEC.md 27.5).

Port of research/scripts/rewrite_scripts.py (which ran its analysis at import over hard-coded D:/ paths): converts
the XML1 BehavEd scripts into XML2 PC form, from P1's trees and P2's mission plan, into the research layout the
build reads as `scripts/out` (Sources override):

    out/scripts/**.py            every XML1 script (bundle scripts, then assets-only scripts), CRLF
    out/scripts/x1/*.py          generated helper scripts (mission starts, long inline code, zone act scripts)
    out/dialogs/x1/*.xml|.XMLB|.engb   dialogs generated from XML1 inline createPopupDialog sequences
    out/data/missions/*.xml|.XMLB|.engb  P2's planned mission text files, compiled
    out/inline_rewrites.json     {original inline code: replacement} for every inline script in XML1 data
    out/helper_refs.json         which helper scripts each source references
    out/zone_acts.json           the act of every XML1 zone and the zone script that can carry setCurrentAct
    out/zone_extra_files.json    zone -> generated files its package must list
    out/var_storage.json         where every XML1 variable lives in XML2
    rewrite_report.txt / .json   counts per rule, everything left unhandled, validation result (next to out/)

Everything is derived from evidence gathered with the research tools (research/scripts: api_diff.txt = the
registered script functions of both executables, var_zones.json = zone-precise use of mission vars / flags / game
vars; P2's mission plan = XML1 missions -> XML2 act groups; SPEC.md section 6). Key engine facts this relies on
(addresses in XMen2.exe unless noted):
  * a script line whose function is unknown, whose arg count differs from the registered signature, or whose literal
    arg type is wrong is silently DROPPED (0x4d8970 returns 0, caller 0x4da517 ignores it)
  * XML1 mission vars/flags live in the store XML2 calls "zone vars" (identical code: XML1 0xcb780 / XML2 0x4d7060,
    32 names, names < 12 chars) but XML2 clears it on EVERY zone load (0x49fe70) while XML1 only clears it when the
    new zone is in a different map directory (xbe 0x99b90 + 0x824c0).
    -> persistent XML1 vars are mapped onto XML2 GAME flags (0x4d7130: 100 names, saved in savegame).
  * XML2 has no integer game-var setter; game vars are only reachable bit-wise via setGameFlag / getGameFlag (bit
    index 1..32, 0x4a0120 / 0x4a0190) -> ints are stored as bit fields.
  * inline script strings are copied into a 255-byte buffer (0x4a12b5) and split on the literal 4 characters \\n\\r
    (0x68d348) -> longer inline code is moved into a helper script file.

Differences from the research generator, none of which changes a byte on Owen's PC (tools/prepare_equiv.py
--scripts compares every file with research/scripts/out):
  * the trees are walked in NTFS directory order on every file system (names sorted by their upper-case form: what
    FindFirstFile returns on NTFS), so the order-dependent outputs (dialog / helper numbering, inline_rewrites.json
    and zone_acts.json key order) are the same on Linux;
  * the "skip scripts/ and packages/ folders" test of the inline-code scan looks at the path below the tree root,
    not the whole path (a cache under ...\\AppData\\Local\\Packages\\... would have skipped every file);
  * all state lives in one Rewriter object per run instead of module globals, and files are written with explicit
    CRLF where the generator relied on Windows text mode.

Cache: <cache>/<disc_id>/prepared/scripts-v<VERSION>-<key[:12]>/; key = VERSION + P1's key + the sha1 of P2's
mission plan and mission texts + the sha1 of the two API tables (research/scripts/xml{1,2}_api.json, packaged
data)."""
from __future__ import annotations

import collections
import json
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from . import check_cancel, digest, ntfs_walk, publish, read_stage, rmtree, sha1_file
from . import disc as P1, tables as P2
from .. import common as C                           # noqa: F401 - puts tools/ (xmlb) on sys.path
from ..lib.bescript import parse_file, parse_line
from ..sources import REPO_ROOT

import xmlb  # noqa: E402  tools/xmlb.py

STAGE = 'scripts'
VERSION = 1
OUT = 'out'                                          # the research layout: Sources overrides scripts/out with this
REPORT_TXT, REPORT_JSON = 'rewrite_report.txt', 'rewrite_report.json'
API_RELS = ('scripts/xml1_api.json', 'scripts/xml2_api.json')   # research-relative, packaged data
NEWLINE = '\r\n'

XML2_ENGINE_GAMEVARS = {'danv', 'r_d_disc', 'r_imarmor', 'r_t_station'}   # set by XMen2.exe itself
INLINE_MAX = 255
STORE_FUNCS = {'setMissionVar': ('mvar', 'set'), 'getMissionVar': ('mvar', 'get'),
               'setMissionFlag': ('mflag', 'set'), 'getMissionFlag': ('mflag', 'get'),
               'setGameVar': ('gvar', 'set'), 'getGameVar': ('gvar', 'get'),
               'disallowResponseOnVar': ('mflag', 'get')}
WIDE_SOURCES = {'getID', 'getIDString', 'getHealth', 'getHealthMax', 'fmul', 'fdiv', 'fadd', 'fsub', 'spawn',
                'getPosX', 'getPosY', 'getPosZ', 'getName', 'getTimeRemaining', 'getNearestMonsterSpawner'}
COUNTER_BITS = 8
TMP = ('x1_t', 'x1_q', 'x1_r', 'x1_b')
DROP = {  # function -> reason (evidence)
    'displayEx': 'XML1 stub (xbe 0x2123a0: xor eax,eax; ret) - no effect in XML1 either',
    'magnetoBall': 'XML1 stub (xbe 0x2123a0) - no effect in XML1 either',
    'xtremeConversationLight': 'no XML2 equivalent (XML1 xbe 0x9e310 toggles the conversation light)',
    'setPowerStatus': 'no XML2 script function to enable/disable a single power (XML1 xbe 0x9db60)',
    'removeFromGroup': 'no XML2 script function (XML1 xbe 0x9fbd0 removes a hero from the party)',
    'exitSoloMode': 'XML2 has no solo mode script API (XML1 xbe 0x9ef70)',
    'enterSoloMode': 'XML2 has no solo mode script API (XML1 xbe 0x9eef0)',
    'setGroupLeader': 'no XML2 equivalent (XML1 xbe 0x9fcd0)',
    'canCancelDialog': 'canCancelDialog outside a popup sequence has no effect',
    'main': 'legacy Python entry call; the engine skips main() (exe 0x4d9cf2)',
}
RENAME = {'screenFade': 'cameraFade',          # XML1 registers both names to 0x98ec0
          'loadMap': 'loadMapKeepTeam'}        # XML1 loadMap = "loadmap %s" (0x9a850); XML2 loadMap
#                                                sends "loadmapaddteam %s", loadMapKeepTeam "loadmap %s 0 0"
MULTIPART = {'juggernaut': ('3401_helmet', '3401_head', 'Bip01 Head', 'explode/JuggernautHelmet'),
             'jailedjuggy': ('3401_helmet', '3401_head', 'Bip01 Head', 'explode/JuggernautHelmet')}


# ============================================================================================== helpers (pure)
def zdir(zone):
    return zone.rsplit('/', 1)[0] if '/' in zone else zone


def split_inline(code):
    return [s for s in re.split(r'\\n\\r|\\r\\n|\\n|\n|\r', code.replace('&apos;', "'").replace('&quot;', '"'))]


def bitlen(n):
    return max(1, int(n).bit_length())


class Storage:
    """kind: 'flag' -> 1:1 game var <gname>, bits 1..nbits (flag bits keep their XML1 numbers)
             'pack' -> bits off+1..off+nbits of game var <gname>
             'zone' -> XML2 zone var <gname> (full int, lives for one zone visit)"""
    def __init__(self, kind, gname, off=0, nbits=1, clearable=True, signed=False):
        self.kind, self.gname, self.off, self.nbits, self.clearable = kind, gname, off, nbits, clearable
        self.signed = signed

    def as_json(self):
        return {'kind': self.kind, 'gamevar': self.gname, 'first_bit': self.off + 1, 'nbits': self.nbits,
                'signed': self.signed, 'cleared_on_mission_start': self.clearable}


class VarInfo:
    def __init__(self, name):
        self.name = name
        self.kinds = set()
        self.lits = set()          # literal values assigned with set*Var
        self.var_set = False       # assigned from a script variable / expression
        self.bits = set()          # literal bit indexes used with *Flag
        self.dyn_bits = False
        self.zones = set()
        self.set_zones = set()
        self.get_zones = set()
        self.n = 0


def q(s, quote='"'):
    if quote == '"' and '"' in s:
        quote = "'"
    return f'{quote}{s}{quote}'


def call(name, *args):
    return f'{name}({", ".join(str(a) for a in args)} )' if args else f'{name}( )'


def argtxt(a, quote):
    if a.kind == 'str':
        return q(a.value, quote)
    return a.text


def gen_get(target, st, quote):
    g = q(st.gname, quote)
    if st.kind == 'zone':
        return [f'{target} = {call("getZoneVar", g)}']
    lines = [f'{target} = {call("getGameFlag", g, st.off + 1)}']
    for i in range(1, st.nbits):
        lines += [f'x1_b = {call("getGameFlag", g, st.off + i + 1)}',
                  f'x1_b = {call("imul", "x1_b", 1 << i)}',
                  f'{target} = {call("iadd", target, "x1_b")}']
    if st.signed:
        # two's complement sign extension; the extra lines are indented by the caller's indent
        lines += ['# ( "x1 sign-extend" )',
                  f'if {target} >= {1 << (st.nbits - 1)}',
                  f'     {target} = {call("isub", target, 1 << st.nbits)}',
                  'endif']
    return lines


def fmt_line(indent, s):
    return indent + s


def compact(stmt):
    """drop whitespace outside quoted strings"""
    out, qc = [], None
    for ch in stmt:
        if qc:
            out.append(ch)
            if ch == qc:
                qc = None
        elif ch in '\'"':
            qc = ch
            out.append(ch)
        elif ch not in ' \t':
            out.append(ch)
    return ''.join(out)


def write_crlf(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = '\r\n'.join(lines) + '\r\n'
    with open(path, 'wb') as fh:
        fh.write(data.encode('latin-1'))


def write_text(path, text, encoding='latin-1'):
    """what open(path, 'w') wrote on Windows: every '\\n' -> CRLF."""
    with open(path, 'wb') as fh:
        fh.write(text.replace('\n', NEWLINE).encode(encoding))


def write_json(path, obj):
    """json.dump(obj, open(path, 'w'), indent=1) as it ran on Windows (ASCII, CRLF)."""
    write_text(path, json.dumps(obj, indent=1), 'ascii')


# ============================================================================================== the rewriter
class Rewriter:
    """One run of the script conversion over XML1 trees (loose = the unpacked bundles + _fb_manifest.json, assets =
    assetsfb.zip minus the bundles) with a mission plan (P2) and the two engines' registered script functions.
    The constructor runs the analysis passes (variable stores, storage plan, missions, side missions); write(out)
    writes the outputs and returns the report lines."""

    def __init__(self, loose, assets, plan, api1, api2, cancel=None):
        self.LOOSE = Path(loose).as_posix()
        self.ASSETS = Path(assets).as_posix()
        self.API1, self.API2, self.PLAN = api1, api2, plan
        self.cancel = cancel
        with open(f'{self.LOOSE}/{P1.MANIFEST}') as fh:
            self.MANIFEST = json.load(fh)
        self.STATS = collections.Counter()
        self.PROBLEMS = []          # (where, message)
        self.HELPER_REFS = collections.defaultdict(set)
        self.STRINGS1 = self.load_strings()
        self.SCRIPT_ZONES = collections.defaultdict(set)      # 'nyc/alison/tut1' -> zones
        self.DATA_ZONES = collections.defaultdict(set)        # 'conversations/x.eng' -> zones
        for b, files in self.MANIFEST.items():
            if b.startswith('packages/generated/maps/'):
                zone = b[len('packages/generated/maps/'):-3]
                for f, k in files:
                    fl = f.lower()
                    if fl.startswith('scripts/') and fl.endswith('.py'):
                        self.SCRIPT_ZONES[fl[8:-3]].add(zone)
                    elif fl.endswith('.eng'):
                        self.DATA_ZONES[fl].add(zone)
        self.ZONE_MISSION = {}
        for dp, dn, fn in ntfs_walk(f'{self.LOOSE}/maps'):
            for f in fn:
                if f.endswith('.eng'):
                    p = f'{dp}/{f}'
                    with open(p, encoding='latin-1') as fh:
                        m = re.search(r'<entity name="world"[^>]*\bmission="([^"]*)"', fh.read(6000))
                    self.ZONE_MISSION[p[len(self.LOOSE) + 6:-4].lower()] = (m.group(1).lower() if m else '')
        self.SCRIPTS = self.script_files()
        self.SCRIPT_BY_REL = {r: p for r, p, o in self.SCRIPTS}
        check_cancel(cancel)

        # ---- pass 1: every variable-store access (scripts + inline data code)
        self.VARS = {}
        self.DYNAMIC_NAME_SITES = []
        self.VALUE_SOURCES = collections.defaultdict(set)   # (store, name) -> functions that produced stored values
        for rel, p, origin in self.SCRIPTS:
            zones = set(self.SCRIPT_ZONES.get(rel, ()))
            last = {}
            for ln in parse_file(p).lines:
                if ln.kind == 'assign':
                    last[ln.target] = ln.value.value.name if ln.value.kind == 'call' else ln.value.kind
            for ln, c, ctx in parse_file(p).calls():
                if c.name in STORE_FUNCS and c.name != 'disallowResponseOnVar':
                    self.note_access(c, zones, f'scripts/{rel}.py:{ln.no}')
                    if c.name in ('setMissionVar', 'setGameVar') and len(c.args) == 2 and \
                            c.args[0].kind == 'str' and c.args[1].kind == 'ident':
                        self.VALUE_SOURCES[('g' if c.name == 'setGameVar' else 'm', c.args[0].value.lower())].add(
                            last.get(c.args[1].text, '?'))
        self.INLINE = list(self.inline_codes())
        for key, attr, code, zones in self.INLINE:
            for piece in split_inline(code):
                ln = parse_line(0, piece)
                cl = [ln.call] if ln.kind == 'call' else (
                    [ln.value.value] if ln.kind == 'assign' and ln.value.kind == 'call' else [])
                for c in cl:
                    if c.name in STORE_FUNCS:
                        self.note_access(c, zones, f'{key} {attr}')
        check_cancel(cancel)

        # ---- storage planning
        self.STORAGE = {}
        self.VAR_DIRS = {}
        self.PACKS = self.plan_storage()
        self.GAMEVAR_NAMES = sorted({s.gname for s in self.STORAGE.values() if s.kind != 'zone'})

        # ---- missions, side missions
        self.MISSIONS = self.PLAN['missions']
        self.MISSION_DIRS = {m: self.mission_dirs(m) for m in self.MISSIONS}
        self._BEGIN_CACHE = {}
        self.SIDE_CALLS = collections.defaultdict(set)     # side mission -> zones of the beginSideMission call sites
        self.SIDE_PARENT = {}
        self.collect_side_calls()
        self.DIALOGS = {}      # key -> (name, element)
        self.HELPERS = {}      # tuple(lines) -> name

    def problem(self, where, msg):
        self.PROBLEMS.append((where, msg))

    # ------------------------------------------------------------------------------------------ XML1 data
    def load_strings(self):
        with open(f'{self.ASSETS}/data/strings.eng', encoding='latin-1') as fh:
            t = fh.read()
        return {m.group(1): m.group(2) for m in re.finditer(r'<string id="(\d+)" text="([^"]*)"', t)}

    def script_files(self):
        """[(rel 'dir/name' lowercase without .py, abs path, origin)] - loose first, assets-only after"""
        out, seen = [], set()
        for root, origin in ((f'{self.LOOSE}/scripts', 'loose'), (f'{self.ASSETS}/scripts', 'assets')):
            for dp, dn, fn in ntfs_walk(root):
                for f in sorted(fn):
                    if f.lower().endswith('.py'):
                        p = f'{dp}/{f}'
                        rel = p[len(root) + 1:-3].lower()
                        if rel in seen:
                            continue
                        seen.add(rel)
                        out.append((rel, p, origin))
        return sorted(out)

    def note_access(self, c, zones, where):
        kind, op = STORE_FUNCS[c.name]
        if not c.args:
            return
        a0 = c.args[0]
        if a0.kind != 'str':
            self.DYNAMIC_NAME_SITES.append(where)
            return
        # XML1 has two stores: mission (vars+flags) and game.  Names compare with _stricmp in both engines
        # (store tree compare xbe 0x14ea30 -> 0x343612, exe 0x4d5b50 -> 0x672562 = MSVCR71 _stricmp)
        key = ('g' if kind == 'gvar' else 'm', a0.value.lower())
        v = self.VARS.setdefault(key, VarInfo(a0.value))
        v.kinds.add(kind)
        v.n += 1
        v.zones |= zones
        if op == 'set':
            v.set_zones |= zones or {'<unbundled>'}
        else:
            v.get_zones |= zones or {'<unbundled>'}
        if kind == 'mflag' and len(c.args) >= 2:
            b = c.args[1]
            if b.kind == 'num':
                v.bits.add(int(b.value))
            else:
                v.dyn_bits = True
        if op == 'set' and kind in ('mvar', 'gvar') and len(c.args) >= 2:
            val = c.args[1]
            if val.kind == 'num':
                v.lits.add(int(val.value))
            else:
                v.var_set = True

    def inline_codes(self):
        """yield (relpath, attr, value, zones) for every inline-code attribute in XML1 English/neutral data"""
        seen = set()
        for root in (self.LOOSE, self.ASSETS):
            for dp, dn, fn in ntfs_walk(root):
                below = dp[len(root):]                   # the research generator tested the whole path
                if '/scripts' in below or '/packages' in below:
                    continue
                for f in fn:
                    fl = f.lower()
                    if not fl.endswith(('.eng', '.xml', '.chr', '.nav')):
                        continue
                    p = f'{dp}/{f}'
                    rel = p[len(root) + 1:]
                    key = rel.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    with open(p, encoding='latin-1') as fh:
                        t = fh.read()
                    zones = set(self.DATA_ZONES.get(key, ()))
                    if key.startswith('maps/'):
                        zones = {key[5:].rsplit('.', 1)[0]}
                    for m in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"]*)"', t):
                        if '(' in m.group(2) and re.search(r'[A-Za-z_]\w*\s*\(', m.group(2)):
                            yield key, m.group(1), m.group(2), zones

    # ------------------------------------------------------------------------------------------ storage planning
    def plan_storage(self):
        packs = {'x1v': [], 'x1g': []}          # prefix -> list of used-bit counts per pack
        VARS, STORAGE, VAR_DIRS, STATS = self.VARS, self.STORAGE, self.VAR_DIRS, self.STATS

        def alloc(prefix, n):
            lst = packs[prefix]
            for i, used in enumerate(lst):
                if used + n <= 32:
                    lst[i] += n
                    return f'{prefix}{i + 1:02d}', used
            lst.append(n)
            return f'{prefix}{len(lst):02d}', 0

        # 1) any name used bit-wise (mission flags, disallowResponseOnVar) keeps its own game var so that
        #    conversation conditions disallowResponseOnVar('mansion2', 7) keep working unchanged
        for name in sorted(VARS, key=lambda k: (k[1].lower(), k[0])):
            v = VARS[name]
            VAR_DIRS[name] = sorted({zdir(z) for z in v.zones})
            if 'mflag' in v.kinds:
                need = max(v.bits | {0})
                if v.lits:
                    need = max(need, max(bitlen(x) for x in v.lits))
                if v.var_set or v.dyn_bits:
                    need = 32 if v.dyn_bits else max(need, COUNTER_BITS)
                g = name[1] if name[1].lower() not in XML2_ENGINE_GAMEVARS else ('x1_' + name[1])[:11]
                STORAGE[name] = Storage('flag', g, 0, min(32, max(need, 1)), clearable=True)
                STATS['storage: 1:1 game var (flag name)'] += 1
        # 2) plain integer vars
        for name in sorted(VARS, key=lambda n: (VAR_DIRS[n], n[1].lower(), n[0])):
            if name in STORAGE:
                continue
            v = VARS[name]
            bundled = '<unbundled>' not in (v.set_zones | v.get_zones)
            single_zone = bundled and len(v.zones) == 1
            # entity ids / health / positions are only meaningful inside the zone that produced them and do
            # not fit a small bit field; every zone that reads such a var also writes it
            wide_local = bundled and self.VALUE_SOURCES.get(name, set()) & WIDE_SOURCES and \
                v.get_zones <= v.set_zones
            if v.var_set and 'gvar' not in v.kinds and (single_zone or wide_local):
                STORAGE[name] = Storage('zone', name[1])
                STATS['storage: XML2 zone var (single-zone counter)' if single_zone else
                      'storage: XML2 zone var (per-zone entity id / health value)'] += 1
                continue
            signed = any(x < 0 for x in v.lits)
            mag = [bitlen(abs(x)) + (1 if signed else 0) for x in v.lits]
            if v.var_set:
                n = max([COUNTER_BITS] + mag)
            else:
                n = max(mag or [1])
            if signed:
                STATS['storage: signed (two\'s complement) packed var'] += 1
            prefix = 'x1g' if 'gvar' in v.kinds else 'x1v'
            g, off = alloc(prefix, n)
            STORAGE[name] = Storage('pack', g, off, n, clearable=(prefix == 'x1v'), signed=signed)
            STATS[f'storage: packed {"game" if prefix == "x1g" else "mission"} var '
                  f'({"counter" if v.var_set else "literal"})'] += 1
        return packs

    # ------------------------------------------------------------------------------------------ code generation
    def gen_set(self, st, val, quote, where):
        """val: Arg (num literal or variable/expression)"""
        g = q(st.gname, quote)
        if st.kind == 'zone':
            return [call('setZoneVar', g, argtxt(val, quote))]
        if val.kind in ('call', 'expr', 'empty'):
            self.problem(where, f'store value is an expression ({val.text}); copied through iadd')
        if val.kind == 'num':
            x = int(val.value)
            lo, hi = (-(1 << (st.nbits - 1)), 1 << (st.nbits - 1)) if st.signed else (0, 1 << st.nbits)
            if not lo <= x < hi:
                self.problem(where, f'value {x} does not fit {st.nbits} bits of {st.gname}; stored modulo 2^{st.nbits}')
            x &= (1 << st.nbits) - 1
            return [call('setGameFlag', g, st.off + i + 1, (x >> i) & 1) for i in range(st.nbits)]
        if st.nbits == 1 and not st.signed:
            # a 0/1 flag assigned from a variable: setGameFlag tests value != 0
            return [call('setGameFlag', g, st.off + 1, val.text)]
        lines = [f'x1_t = {call("iadd", val.text, 0)}']
        if st.signed:
            # bias negative runtime values into two's complement before splitting into bits
            lines += ['# ( "x1 sign-extend" )',
                      'if x1_t < 0',
                      f'     x1_t = {call("iadd", "x1_t", 1 << st.nbits)}',
                      'endif']
        for i in range(st.nbits):
            lines += [f'x1_q = {call("idiv", "x1_t", 2)}',
                      f'x1_r = {call("imul", "x1_q", 2)}',
                      f'x1_r = {call("isub", "x1_t", "x1_r")}',
                      call('setGameFlag', g, st.off + i + 1, 'x1_r')]
            if i + 1 < st.nbits:
                lines.append(f'x1_t = {call("iadd", "x1_q", 0)}')
        return lines

    def gen_clear(self, names, quote='"'):
        lines = []
        for n in sorted(names, key=lambda k: (k[1].lower(), k[0])):
            st = self.STORAGE[n]
            if st.kind == 'zone' or not st.clearable:
                continue
            bits = range(st.off + 1, st.off + st.nbits + 1)
            if st.kind == 'flag':
                v = self.VARS[n]
                used = v.bits | set(range(1, (st.nbits if (v.lits or v.var_set) else 0) + 1))
                bits = sorted(used) if used and not v.dyn_bits else range(1, st.nbits + 1)
            lines += [call('setGameFlag', q(st.gname, quote), b, 0) for b in bits]
        return lines

    # ------------------------------------------------------------------------------------------ missions
    def mission_dirs(self, m):
        info = self.MISSIONS.get(m, {})
        dirs = {zdir(z) for z, mm in self.ZONE_MISSION.items() if mm == m}
        ml = (info.get('attrs') or {}).get('mapload', '')
        if ml:
            dirs.add(zdir(ml.lower()))
        ss = (info.get('attrs') or {}).get('scriptstart', '')
        if ss and ss.lower() in self.SCRIPT_BY_REL:
            with open(self.SCRIPT_BY_REL[ss.lower()], encoding='latin-1') as fh:
                text = fh.read()
            for m2 in re.finditer(r"load(?:Map|Zone)\s*\(\s*['\"]([^'\"]+)", text):
                dirs.add(zdir(m2.group(1).lower()))
        return dirs

    def mission_begin_lines(self, m, depth=0):
        """statement list equivalent to XML1 beginMission(m) (console 'beginmission', xbe 0x18da90)"""
        m = m.lower()
        if m in self._BEGIN_CACHE:
            return list(self._BEGIN_CACHE[m])
        info = self.MISSIONS.get(m)
        lines = [f'# ( "XML1 beginMission({m})" )']
        if info is None:
            self.problem(f'mission {m}', 'beginMission target has no XML1 mission file - only the call is dropped')
            return lines
        dirs = self.MISSION_DIRS[m]
        lines += self.gen_clear([n for n in self.VARS if self.STORAGE[n].kind != 'zone' and
                                 set(self.VAR_DIRS[n]) & dirs])
        lines.append(call('setCurrentAct', info['act']))
        for o in info.get('objectives', []):
            on = q(o['name'])
            lines.append(call('objective', on, '"EOBJCMD_INCOMPLETE"'))
            lines.append(call('objective', on, '"EOBJCMD_SHOW"' if o.get('enabled', 'false').lower() == 'true'
                              else '"EOBJCMD_HIDE"'))
        for h in info.get('required', []):
            lines.append(call('unlockCharacter', q(h.lower()), '""'))
        attrs = info.get('attrs') or {}
        ss = attrs.get('scriptstart', '').strip().lower()
        ml = attrs.get('mapload', '').strip()
        if ss and ss in self.SCRIPT_BY_REL and depth < 3:
            body, _ = self.rewrite_script_lines(parse_file(self.SCRIPT_BY_REL[ss]), f'scripts/{ss}.py', depth + 1)
            lines += [x.strip() for x in body if x.strip() and not x.strip().startswith('#')]
        elif ml:
            fn = 'loadMapChooseTeam' if attrs.get('teamselect', '').lower() == 'true' else 'loadMapKeepTeam'
            lines.append(call(fn, q(ml)))
        self._BEGIN_CACHE[m] = lines
        return list(lines)

    # side missions: XML1 'beginsidemission' = pushsidemission + beginmission (xbe 0x18dd70);
    # 'endsidemission' == XML2 'restorelastzone' (xbe 0x18df20 vs exe 0x5f4580, same code).  XML2 has
    # no script function that pushes the zone, so returns are resolved statically.
    def collect_side_calls(self):
        for rel, p, origin in self.SCRIPTS:
            for ln, c, ctx in parse_file(p).calls():
                if c.name == 'beginSideMission' and c.args and c.args[0].kind == 'str':
                    self.SIDE_CALLS[c.args[0].value.lower()] |= self.SCRIPT_ZONES.get(rel, set())
        for key, attr, code, zones in self.INLINE:
            for m in re.finditer(r"beginSideMission\s*\(\s*['\"]([^'\"]+)", code):
                self.SIDE_CALLS[m.group(1).lower()] |= zones
        order = list(self.MISSIONS)
        for s, zones in self.SIDE_CALLS.items():
            parents = {self.ZONE_MISSION.get(z, '') for z in zones} - {''}
            if not parents:
                # caller zone has no world mission= attribute: use the first campaign mission owning its directory
                owners = [m for m in order if m != s and {zdir(z) for z in zones} & self.MISSION_DIRS.get(m, set())]
                parents = set(owners[:1])
            self.SIDE_PARENT[s] = sorted(parents)

    def side_mission_for(self, zones):
        dirs = {zdir(z) for z in zones}
        return [s for s in self.SIDE_CALLS if self.MISSION_DIRS.get(s, set()) & dirs]

    def end_side_lines(self, zones, where, quote='"'):
        cands = self.side_mission_for(zones)
        if len(cands) != 1:
            self.problem(where, f'endSideMission: cannot tell which side mission ends (candidates {cands}); '
                                'falling back to XML2 restorelastzone("1") which needs a pushed side mission')
            return [call('restorelastzone', q('1', quote))]
        s = cands[0]
        back = sorted(self.SIDE_CALLS[s])
        lines = [f'# ( "XML1 endSideMission from side mission {s}" )']
        parents = self.SIDE_PARENT.get(s, [])
        if len(parents) == 1 and parents[0] in self.MISSIONS:
            lines.append(call('setCurrentAct', self.MISSIONS[parents[0]]['act']))
        if not back:
            self.problem(where, f'endSideMission({s}): caller zone unknown, using restorelastzone')
            return lines + [call('restorelastzone', q('1', quote))]
        if len(back) > 1:
            self.problem(where, f'endSideMission({s}): side mission started from several zones {back}; '
                                f'returning to {back[0]}')
        lines.append(call('loadZone', q(back[0], quote), q('', quote)))
        return lines

    # ------------------------------------------------------------------------------------------ dialogs
    # generated from createPopupDialog/addPopupDialogOption/canCancelDialog/showPopupDialog
    def resolve_text(self, s):
        m = re.fullmatch(r'\$(\d+)', s.strip())
        if m:
            if m.group(1) in self.STRINGS1:
                self.STATS['dialog text $id resolved from XML1 strings.eng'] += 1
                return self.STRINGS1[m.group(1)]
            self.problem('dialog', f'string id {s} not in XML1 strings.eng')
        return s

    def make_dialog(self, title, options, cancancel, where):
        el = ET.Element('dialog')
        attrs = {'text': self.resolve_text(title)}
        if cancancel is not None:
            attrs['cancancel'] = 'true' if cancancel else 'false'
        if not options:
            # message-only popup: same accept prompt XML1/XML2 hint dialogs declare (e.g. XML1 dialogs/tut1,
            # XML2 Dialogs/act1/genosha/throw_hint)
            attrs['help1'] = ' '
            attrs['help2'] = '$MENU_ACCEPT Continue'
        el.attrib = dict(sorted(attrs.items()))
        for text, script in options:
            o = ET.SubElement(el, 'option')
            oa = {'text': self.resolve_text(text)}
            if script:
                oa['script'] = self.rewrite_inline(script, where + ' popup option', console=True)
            o.attrib = dict(sorted(oa.items()))
        key = ET.tostring(el, encoding='unicode')
        if key not in self.DIALOGS:
            self.DIALOGS[key] = (f'x1/p{len(self.DIALOGS) + 1:03d}', el)
        return self.DIALOGS[key][0]

    # ------------------------------------------------------------------------------------------ helper scripts
    # (for code too long / too complex for inline strings)
    def helper_script(self, lines, hint):
        key = tuple(lines)
        if key not in self.HELPERS:
            base = re.sub(r'[^a-z0-9_]', '_', hint.lower())[:24]
            name = f'x1/{base}'
            n = 2
            while name in self.HELPERS.values():
                name = f'x1/{base}_{n}'
                n += 1
            self.HELPERS[key] = name
        return self.HELPERS[key]

    # ------------------------------------------------------------------------------------------ statement rewriting
    def rewrite_call(self, c, target, zones, where, quote, depth):
        """return list of statements replacing `[target = ]c(...)`, or None to keep the line"""
        name = c.name
        STATS = self.STATS
        if name in STORE_FUNCS and name != 'disallowResponseOnVar':
            kind, op = STORE_FUNCS[name]
            a0 = c.args[0] if c.args else None
            STATS[f'rule {name}'] += 1
            if a0 is None:
                return ['# ( "x1: empty store call removed" )']
            if a0.kind != 'str':
                # runtime-computed name (hive/h_int/hive_trigger_rescue.py): only the zone store takes it
                fn = {'getMissionVar': 'getZoneVar', 'setMissionVar': 'setZoneVar', 'getMissionFlag': 'getZoneFlag',
                      'setMissionFlag': 'setZoneFlag', 'getGameVar': 'getZoneVar', 'setGameVar': 'setZoneVar'}[name]
                self.problem(where, f'{name} with runtime name {a0.text} -> {fn} (zone lifetime)')
                s = call(fn, *[argtxt(a, quote) for a in c.args])
                return [f'{target} = {s}' if target else s]
            st = self.STORAGE[('g' if kind == 'gvar' else 'm', a0.value.lower())]
            if kind == 'mflag':
                bit = argtxt(c.args[1], quote) if len(c.args) > 1 else '1'
                gf = 'ZoneFlag' if st.kind == 'zone' else 'GameFlag'
                if st.kind == 'pack':
                    if c.args[1].kind != 'num':
                        self.problem(where, 'flag op with runtime bit on a packed var')
                    bit = st.off + int(c.args[1].value)
                if op == 'get':
                    return [f'{target} = {call("get" + gf, q(st.gname, quote), bit)}'] if target else []
                val = argtxt(c.args[2], quote) if len(c.args) > 2 else '1'
                return [call('set' + gf, q(st.gname, quote), bit, val)]
            if op == 'get':
                if not target:
                    return ['# ( "x1: unused get removed" )']
                return gen_get(target, st, quote)
            if len(c.args) < 2:
                self.problem(where, f'{name} without value')
                return []
            return self.gen_set(st, c.args[1], quote, where)
        if name == 'disallowResponseOnVar' and c.args and c.args[0].kind == 'str':
            st = self.STORAGE.get(('m', c.args[0].value.lower()))
            if st and st.kind == 'pack' and c.args[1].kind == 'num':
                STATS['rule disallowResponseOnVar (packed var)'] += 1
                return [call(name, q(st.gname, quote), st.off + int(c.args[1].value))]
            if st and st.gname.lower() != c.args[0].value.lower():
                return [call(name, q(st.gname, quote), argtxt(c.args[1], quote))]
            return None
        if name in RENAME:
            STATS[f'rule {name} -> {RENAME[name]}'] += 1
            s = call(RENAME[name], *[argtxt(a, quote) for a in c.args])
            return [f'{target} = {s}' if target else s]
        if name in ('beginMission', 'beginMissionHack', 'beginSideMission') and c.args and c.args[0].kind != 'str':
            self.problem(where, f'{name} with non-literal mission name {c.args[0].text} - left unchanged '
                                f'(no-op in XML2)')
            return None
        if name in ('beginMission', 'beginMissionHack') and c.args and c.args[0].kind == 'str':
            STATS[f'rule {name}'] += 1
            return self.mission_begin_lines(c.args[0].value, depth)
        if name == 'beginSideMission' and c.args and c.args[0].kind == 'str':
            STATS['rule beginSideMission'] += 1
            s = c.args[0].value.lower()
            return [f'# ( "XML1 beginSideMission({s}) - return handled by endSideMission rewrite" )'] + \
                self.mission_begin_lines(s, depth)
        if name == 'endSideMission':
            STATS['rule endSideMission'] += 1
            return self.end_side_lines(zones, where, quote)
        if name == 'setInCampaign':
            STATS['rule setInCampaign'] += 1
            if len(c.args) == 2 and c.args[1].kind == 'str' and c.args[1].value.upper() == 'TRUE':
                # XML2 unlockCharacter (0x49f520) does the same registry->vtbl+0x2c(vtbl+0x3c(name))
                return [call('unlockCharacter', argtxt(c.args[0], quote), q('', quote))]
            return ['# ( "x1: setInCampaign FALSE is a no-op in XML1 (xbe 0x99460)" )']
        if name == 'addHero':
            STATS['rule addHero'] += 1
            self.problem(where, 'addHero: XML2 cannot add a hero to the party from script; hero is unlocked and the '
                                'team menu (extractionPointLite) is opened instead - verify in game')
            return [call('unlockCharacter', argtxt(c.args[0], quote), q('', quote)),
                    call('extractionPointLite', q('_ACTIVE_HERO_', quote), q('true', quote), q('false', quote),
                         q('false', quote))]
        if name == 'mission' and len(c.args) == 2:
            STATS['rule mission'] += 1
            return [f'# ( "x1: mission({c.args[0].value}, {c.args[1].value}) - XML1 blackbird-menu state, no XML2 '
                    f'equivalent" )']
        if name == 'destroyMultipartPiece':
            STATS['rule destroyMultipartPiece'] += 1
            ent = c.args[0].value.lower() if c.args and c.args[0].kind == 'str' else ''
            if ent in MULTIPART:
                hide, show, bone, fx = MULTIPART[ent]
                e = argtxt(c.args[0], quote)
                return [call('setSegmentVisible', e, q(hide, quote), q('0', quote)),
                        call('setSegmentVisible', e, q(show, quote), q('1', quote)),
                        call('spawnEffectBone', e, q(bone, quote), q(fx, quote))]
            self.problem(where, f'destroyMultipartPiece on unknown entity {ent}')
            return ['# ( "x1: destroyMultipartPiece removed" )']
        if name == 'blackbirdMenu' and len(c.args) == 3 and c.args[1].kind == 'str' and '(' in c.args[1].value:
            # 2nd arg is code run later via 'runscript %s' (xbe 0x167c04 / exe 0x5e08d4)
            new = self.rewrite_inline(c.args[1].value, where + ' blackbirdMenu', frozenset(zones), console=True)
            if new == c.args[1].value:
                return None
            STATS['rule blackbirdMenu code argument'] += 1
            return [call(name, argtxt(c.args[0], quote), q(new, '"' if quote == '"' else "'"),
                         argtxt(c.args[2], quote))]
        if name == 'extractionPointLite' and len(c.args) == 6:
            STATS['rule extractionPointLite 6->4 args'] += 1
            return [call(name, *[argtxt(a, quote) for a in c.args[:4]])]
        if name in DROP:
            STATS[f'drop {name}'] += 1
            txt = f'{name}(' + ', '.join(a.text for a in c.args) + ')'
            return [f'# ( "x1 removed: {txt.replace(chr(34), chr(39))}" )']
        return None

    def rewrite_script_lines(self, sc, where_file, depth=0, zones=None):
        """returns (lines, changed?)"""
        STATS = self.STATS
        if zones is None:
            rel = where_file[8:-3] if where_file.startswith('scripts/') else ''
            zones = self.SCRIPT_ZONES.get(rel, set())
        out = []
        changed = False
        popup = None
        for ln in sc.lines:
            where = f'{where_file}:{ln.no}'
            ind = ln.indent
            if ln.kind in ('blank', 'comment'):
                if popup is None:
                    out.append(ln.raw)
                continue
            if ln.kind in ('import', 'def', 'global', 'from', 'pass', 'return', 'print') or \
                    (ln.kind == 'if' and '__name__' in ln.text):
                STATS['drop legacy python line'] += 1
                out.append(f'{ind}# x1 legacy: {ln.text}')
                changed = True
                continue
            if ln.kind in ('if', 'elif', 'while'):
                if getattr(ln, 'colon', False):
                    STATS['strip trailing ":" on if/elif'] += 1
                    out.append(ind + re.sub(r'\s*:\s*$', '', ln.text))
                    changed = True
                else:
                    out.append(ln.raw)
                continue
            if ln.kind in ('else', 'endif', 'endwhile'):
                out.append(ln.raw)
                continue
            if ln.kind == 'other':
                if ln.text.startswith('global ') or re.fullmatch(r'[A-Za-z_]\w*\s*=\s*', ln.text):
                    STATS['drop invalid statement'] += 1
                    out.append(f'{ind}# x1 invalid: {ln.text}')
                    changed = True
                else:
                    out.append(ln.raw)
                continue
            c = ln.call if ln.kind == 'call' else (
                ln.value.value if ln.kind == 'assign' and ln.value.kind == 'call' else None)
            target = ln.target if ln.kind == 'assign' else None
            if ln.kind == 'assign' and ln.value.kind == 'num':
                # 'x = 0': no XML2 script ever assigns a bare literal; use the registered iadd builtin
                STATS['rule literal assignment -> iadd'] += 1
                out.append(f'{ind}{target} = {call("iadd", ln.value.text, 0)}')
                changed = True
                continue
            if c is None:
                out.append(ln.raw)
                continue
            # popup sequences
            if c.name == 'createPopupDialog':
                popup = {'title': c.args[0].value if c.args else '', 'options': [], 'cancel': None, 'indent': ind}
                STATS['rule createPopupDialog'] += 1
                changed = True
                continue
            if popup is not None and c.name in ('addPopupDialogOption', 'canCancelDialog'):
                if c.name == 'addPopupDialogOption':
                    popup['options'].append((c.args[0].value, c.args[1].value if len(c.args) > 1 else ''))
                else:
                    popup['cancel'] = (c.args[0].value.upper() == 'TRUE') if c.args else None
                continue
            if c.name == 'showPopupDialog':
                if popup is None:
                    self.problem(where, 'showPopupDialog without createPopupDialog')
                    out.append(f'{ind}# x1 removed: showPopupDialog()')
                else:
                    dname = self.make_dialog(popup['title'], popup['options'], popup['cancel'], where)
                    out.append(popup['indent'] + call('createPopupDialogXml', q(dname)))
                    popup = None
                changed = True
                continue
            if c.prefix:
                STATS['strip game. prefix'] += 1
                changed = True
            rep = self.rewrite_call(c, target, zones, where, '"', depth)
            if rep is None:
                if c.prefix:
                    s = call(c.name, *[a.text for a in c.args])
                    out.append(ind + (f'{target} = {s}' if target else s))
                else:
                    out.append(ln.raw)
                continue
            changed = True
            if not [r for r in rep if not r.startswith('#')] and ln.kind != 'comment':
                # keep blocks non-empty: debug() is a registered no-op in XML2 (0x5aaff0)
                rep = rep + [call('debug', '"x1: removed statement"')]
            out += [fmt_line(ind, r) for r in rep]
        if popup is not None:
            self.problem(where_file, 'unterminated createPopupDialog sequence')
        return out, changed

    def rewrite_inline(self, code, where, zones=frozenset(), console=False):
        """rewrite one inline script string (single-quote style).  Returns inline code or a helper path.
        console=True: the string is run as 'runscript <code>' and must be a single whitespace-free token."""
        pieces = [p for p in split_inline(code)]
        stmts = [parse_line(0, p) for p in pieces if p.strip()]
        if len(stmts) == 1 and stmts[0].kind == 'call' and \
                stmts[0].call.name in ('beginMission', 'beginSideMission', 'beginMissionHack') \
                and stmts[0].call.args and stmts[0].call.args[0].kind == 'str' \
                and stmts[0].call.args[0].value.lower() in self.MISSIONS:
            # the whole inline script starts a mission: point at the generated mission start script
            self.STATS[f'rule {stmts[0].call.name} (inline -> x1/missions script)'] += 1
            path = f'x1/missions/begin_{stmts[0].call.args[0].value.lower()}'
            self.HELPER_REFS[path].add(where)
            return path
        out = []
        changed = False
        for piece in pieces:
            if not piece.strip():
                continue
            ln = parse_line(0, piece)
            c = ln.call if ln.kind == 'call' else (
                ln.value.value if ln.kind == 'assign' and ln.value.kind == 'call' else None)
            if c is None:
                out.append(piece.strip())
                continue
            target = ln.target if ln.kind == 'assign' else None
            rep = self.rewrite_call(c, target, set(zones), where, "'", 1)
            if rep is None:
                # unchanged statements stay byte-identical (the engine ignores a 'game.' prefix itself)
                out.append(piece.strip())
            else:
                changed = True
                out += [r for r in rep if not r.startswith('#')]
        if not changed:
            return code
        if not out:
            return "debug('x1')" if console else "debug('x1: removed statement')"
        out = [o.replace('"', "'") for o in out]
        if console:
            # executed through the console as "runscript <code>" (XML2 0x5eb8e3 dialogs, 0x5e08d4 blackbird
            # menu): the console tokenizer (0x55b670) splits on whitespace and ';', so the code must be one
            # token - exactly how XML1/XML2 data writes it: runscript unlockCharacter('','astonishing')
            out = [compact(o) for o in out]
        joined = '\\n\\r'.join(out)
        fits = len(joined) <= (INLINE_MAX - len('runscript ') if console else INLINE_MAX) and len(out) <= 6
        if fits and not (console and re.search(r'[\s;]', joined)):
            return joined
        hname = self.helper_script([x.replace("'", '"') for x in out], re.sub(r'\W+', '_', where.split('/')[-1])[:20])
        self.HELPER_REFS[hname].add(where)
        self.STATS['inline code moved to helper script'] += 1
        return hname

    # ------------------------------------------------------------------------------------------ validation
    # against XMen2.exe's registered signatures (mirrors 0x4d8970)
    def validate_lines(self, lines, where):
        bad = []
        depth = 0
        for i, raw in enumerate(lines, 1):
            ln = parse_line(i, raw)
            if ln.kind == 'if':
                depth += 1
            elif ln.kind == 'endif':
                depth -= 1
            c = ln.call if ln.kind == 'call' else (
                ln.value.value if ln.kind == 'assign' and ln.value.kind == 'call' else None)
            if c is None:
                continue
            e = self.API2.get(c.name)
            if e is None:
                if c.name != 'main':
                    bad.append(f'{where}:{i}: unknown function {c.name}')
                continue
            if len(c.args) != len(e['args']):
                bad.append(f'{where}:{i}: {c.name} argc {len(c.args)} != {len(e["args"])}')
                continue
            for a, t in zip(c.args, e['args']):
                if t in 'if' and a.kind == 'str':
                    bad.append(f'{where}:{i}: {c.name} string literal for {t} parameter')
                if t == 's' and a.kind == 'num':
                    bad.append(f'{where}:{i}: {c.name} number literal for s parameter')
        return bad

    # ------------------------------------------------------------------------------------------ zone acts
    def zone_acts(self):
        """XML2 zone scripts call setCurrentAct(n) on entry (150 calls in XML2's own scripts) so the act's
        objectives are loaded after save/load and zone hops.  Work out the act for every XML1 zone and which
        zone script (world zonescript=, else scripts/<zone>.py) can carry the call."""
        order = list(self.MISSIONS)
        info = {}
        for dp, dn, fn in ntfs_walk(f'{self.LOOSE}/maps'):
            for f in fn:
                if not f.endswith('.eng'):
                    continue
                p = f'{dp}/{f}'
                z = p[len(self.LOOSE) + 6:-4].lower()
                with open(p, encoding='latin-1') as fh:
                    t = fh.read(8000)
                m = re.search(r'<entity name="world"([^>]*)>', t)
                if not m:
                    continue
                zs = re.search(r'zonescript="([^"]*)"', m.group(1))
                script = zs.group(1).replace(chr(92), '/').lower() if zs else (z if z in self.SCRIPT_BY_REL else None)
                ms = self.ZONE_MISSION.get(z, '')
                owners = [ms] if ms in self.MISSIONS else [mm for mm in order
                                                            if zdir(z) in self.MISSION_DIRS.get(mm, set())]
                acts = sorted({self.MISSIONS[mm]['act'] for mm in owners})
                info[z] = {'missions': owners, 'acts': acts, 'zonescript': script,
                           'zonescript_from_attr': bool(zs)}
        # a zonescript can carry setCurrentAct only if every zone using it maps to exactly one act
        by_script = collections.defaultdict(set)
        for z, d in info.items():
            if d['zonescript']:
                by_script[d['zonescript']].add(z)
        inject = {}
        for s, zs in by_script.items():
            acts = {tuple(info[z]['acts']) for z in zs}
            if len(acts) == 1 and len(next(iter(acts))) == 1 and s in self.SCRIPT_BY_REL:
                inject[s] = next(iter(acts))[0]
        for z, d in info.items():
            d['inject_act'] = inject.get(d['zonescript'])
        return info, inject

    # ------------------------------------------------------------------------------------------ outputs
    def write(self, OUT, missions_src=None):
        """write every output under OUT (the research scripts/out layout). missions_src: P2's directory of planned
        mission texts (x1_act*.xml, missions.xml), copied into OUT/data/missions and compiled. Returns
        (report lines, report json object)."""
        STATS, SCRIPTS = self.STATS, self.SCRIPTS
        report = {'files': {}, 'validation': [], 'unchanged': 0, 'changed': 0}
        zinfo, inject = self.zone_acts()
        before_fail = collections.Counter()
        for i, (rel, p, origin) in enumerate(SCRIPTS):
            if i % 100 == 0:
                check_cancel(self.cancel)
            sc = parse_file(p)
            # baseline: how many lines would XMen2.exe drop if the file were copied unchanged
            for x in self.validate_lines([x.raw for x in sc.lines], rel):
                before_fail[origin] += 1
            lines, changed = self.rewrite_script_lines(sc, f'scripts/{rel}.py')
            if rel in inject:
                k = 0
                while k < len(lines) and (not lines[k].strip() or lines[k].lstrip().startswith('#')):
                    k += 1
                lines[k:k] = ['# ( "x1: load this act\'s objectives on zone entry (XML2 zone scripts do the same)" )',
                              call('setCurrentAct', inject[rel])]
                changed = True
                STATS['zone script: setCurrentAct injected'] += 1
            if sc.eol != 'crlf' or not sc.final_newline:
                changed = True
                STATS['normalise line endings / final CRLF'] += 1
            write_crlf(os.path.join(OUT, 'scripts', rel + '.py'), lines)
            report['files'][rel] = {'origin': origin, 'changed': changed}
            report['changed' if changed else 'unchanged'] += 1
            report['validation'] += self.validate_lines(lines, f'scripts/{rel}.py')
        check_cancel(self.cancel)
        # inline data code
        inline_map = {}
        for key, attr, code, zones in self.INLINE:
            console = (key.startswith('dialogs/') or key.startswith('ui/')) and \
                attr.lower() in ('script', 'scriptok', 'scriptcancel')
            new = self.rewrite_inline(code, f'{key} {attr}', frozenset(zones), console=console)
            if new != code:
                inline_map[code] = new
                STATS['inline data strings rewritten'] += 1
        # dialogs
        for key, (name, el) in self.DIALOGS.items():
            base = os.path.join(OUT, 'dialogs', *name.split('/'))
            os.makedirs(os.path.dirname(base), exist_ok=True)
            write_text(base + '.xml', xmlb.to_text(ET.fromstring(key)))
            data = xmlb.encode(el)
            with open(base + '.XMLB', 'wb') as fh:
                fh.write(data)
            with open(base + '.engb', 'wb') as fh:
                fh.write(data)
        # mission files planned by P2 (mission_plan): copy the text, compile it -> XMLB/engb (attributes sorted)
        mdir = os.path.join(OUT, 'data', 'missions')
        if missions_src is not None:
            os.makedirs(mdir, exist_ok=True)
            for f in sorted(os.listdir(missions_src)):
                if f.endswith('.xml'):
                    shutil.copyfile(os.path.join(missions_src, f), os.path.join(mdir, f))
        if os.path.isdir(mdir):
            for f in sorted(os.listdir(mdir)):
                if f.endswith('.xml'):
                    root = ET.parse(os.path.join(mdir, f)).getroot()
                    for el in root.iter():
                        el.attrib = dict(sorted((k.lower(), v) for k, v in el.attrib.items()))
                    data = xmlb.encode(root)
                    base = os.path.join(mdir, f[:-4])
                    with open(base + '.XMLB', 'wb') as fh:
                        fh.write(data)
                    if f != 'missions.xml':
                        with open(base + '.engb', 'wb') as fh:
                            fh.write(data)
        # helper scripts
        for lines, name in self.HELPERS.items():
            write_crlf(os.path.join(OUT, 'scripts', name + '.py'), ['# Generated by rewrite_scripts.py'] + list(lines))
            report['validation'] += self.validate_lines(list(lines), f'scripts/{name}.py')
        # mission start helpers for every planned mission (for data/menus that start missions)
        for m in self.MISSIONS:
            ls = self.mission_begin_lines(m)
            write_crlf(os.path.join(OUT, 'scripts', 'x1', 'missions', f'begin_{m}.py'),
                       ['# Generated by rewrite_scripts.py'] + ls)
            report['validation'] += self.validate_lines(ls, f'scripts/x1/missions/begin_{m}.py')
        # inline validation
        for orig, new in inline_map.items():
            if new.startswith('x1/'):
                continue
            report['validation'] += self.validate_lines(new.replace("\\n\\r", '\n').split('\n'), 'inline')
        write_json(os.path.join(OUT, 'zone_acts.json'), zinfo)
        no_script = sorted(z for z, d in zinfo.items() if not d['zonescript'])
        ambiguous = sorted(z for z, d in zinfo.items() if d['zonescript'] and d['inject_act'] is None)
        self.problem('zones', f'{len(no_script)} zones have no zone script: setCurrentAct only comes from beginMission '
                              f'(give them zonescript=x1/zones/<zone> to be save/load safe): {no_script[:8]}...')
        for z in no_script:
            if len(zinfo[z]['acts']) == 1:
                write_crlf(os.path.join(OUT, 'scripts', 'x1', 'zones', *z.split('/')) + '.py',
                           ['# Generated by rewrite_scripts.py', call('setCurrentAct', zinfo[z]['acts'][0])])
        if ambiguous:
            self.problem('zones', f'{len(ambiguous)} zones belong to missions in different acts; no setCurrentAct '
                                  f'injected: {ambiguous}')
        write_json(os.path.join(OUT, 'inline_rewrites.json'), inline_map)
        write_json(os.path.join(OUT, 'helper_refs.json'), {k: sorted(v) for k, v in self.HELPER_REFS.items()})
        # zone -> generated files it must package (XML2 PKGBs list every script/dialog a zone can run)
        zone_extra = collections.defaultdict(set)

        def zones_of(src):
            src = src.split(':')[0].split(' ')[0].lower()
            if src.startswith('scripts/'):
                return self.SCRIPT_ZONES.get(src[8:-3], set())
            return self.DATA_ZONES.get(src, set()) | ({src[5:].rsplit('.', 1)[0]} if src.startswith('maps/') else set())

        for path, srcs in self.HELPER_REFS.items():
            for s in srcs:
                for z in zones_of(s):
                    zone_extra[z].add(f'scripts/{path}')
        for rel, p, origin in SCRIPTS:
            f = os.path.join(OUT, 'scripts', rel + '.py')
            with open(f, encoding='latin-1') as fh:
                text = fh.read()
            for m in re.finditer(r'createPopupDialogXml\("(x1/[^"]+)"', text):
                for z in self.SCRIPT_ZONES.get(rel, set()):
                    zone_extra[z].add(f'dialogs/{m.group(1)}')
        write_json(os.path.join(OUT, 'zone_extra_files.json'), {z: sorted(v) for z, v in sorted(zone_extra.items())})
        VARS, STORAGE = self.VARS, self.STORAGE
        write_json(os.path.join(OUT, 'var_storage.json'),
                   {f'{n[0]}:{n[1]}': {**STORAGE[n].as_json(), 'xml1_kinds': sorted(VARS[n].kinds),
                                       'dirs': self.VAR_DIRS[n], 'literal_values': sorted(VARS[n].lits),
                                       'set_from_variable': VARS[n].var_set, 'flag_bits': sorted(VARS[n].bits)}
                    for n in sorted(STORAGE, key=lambda k: (k[1].lower(), k[0]))})

        # ---- report
        texts = {}
        for r, p, o in SCRIPTS:
            with open(p, encoding='latin-1') as fh:
                texts[p] = fh.read()
        tmp_clash = [t for t in TMP if any(re.search(r'\b%s\b' % t, texts[p]) for r, p, o in SCRIPTS)]
        long_names = [n for n in self.GAMEVAR_NAMES if len(n) >= 12]
        lines = []
        w = lines.append
        w('rewrite_scripts.py report')
        w(f'scripts processed: {len(SCRIPTS)} (loose bundles {sum(1 for s in SCRIPTS if s[2] == "loose")}, '
          f'assets-only {sum(1 for s in SCRIPTS if s[2] == "assets")}); changed {report["changed"]}, '
          f'unchanged {report["unchanged"]}')
        w(f'lines XMen2.exe would drop if copied unchanged: loose {before_fail["loose"]}, '
          f'assets {before_fail["assets"]}')
        w(f'lines XMen2.exe would drop after rewrite (validation): {len(report["validation"])}')
        for v in report['validation'][:60]:
            w(f'   {v}')
        w(f'generated dialogs: {len(self.DIALOGS)}; helper scripts: {len(self.HELPERS)}; mission start scripts: '
          f'{len(self.MISSIONS)}')
        w(f'inline data strings scanned: {len(self.INLINE)}; rewritten: {len(inline_map)}')
        w(f'XML2 game vars used: {len(self.GAMEVAR_NAMES)} of 100 (XMen2.exe itself uses 4: '
          f'{sorted(XML2_ENGINE_GAMEVARS)})'
          f'; names >= 12 chars: {long_names}; temp var clashes with XML1 scripts: {tmp_clash}')
        w(f'packs: mission x1v* {self.PACKS["x1v"]}, game x1g* {self.PACKS["x1g"]}')
        zone_vars_per_zone = collections.Counter()
        for n, st in STORAGE.items():
            if st.kind == 'zone':
                for z in VARS[n].zones:
                    zone_vars_per_zone[z] += 1
        w(f'max XML2 zone vars needed in one zone: {max(zone_vars_per_zone.values() or [0])} (limit 32)')
        w('')
        w('== rule counts')
        for k, v in sorted(STATS.items()):
            w(f'  {v:6}  {k}')
        w('')
        w(f'== items needing attention ({len(self.PROBLEMS)})')
        agg = collections.defaultdict(list)
        for where, msg in self.PROBLEMS:
            agg[msg].append(where)
        for msg, ws in sorted(agg.items(), key=lambda kv: -len(kv[1])):
            w(f'  [{len(ws)}] {msg}')
            for x in ws[:4]:
                w(f'        {x}')
        rep_json = {'stats': STATS, 'problems': self.PROBLEMS, 'validation': report['validation'],
                    'files': report['files']}
        return lines, rep_json, {'scripts': len(SCRIPTS), 'changed': report['changed'],
                                 'dialogs': len(self.DIALOGS), 'helpers': len(self.HELPERS),
                                 'missions': len(self.MISSIONS), 'inline_scanned': len(self.INLINE),
                                 'inline_rewritten': len(inline_map), 'validation': len(report['validation']),
                                 'problems': len(self.PROBLEMS)}


def write_report(dst_dir, lines, rep_json):
    """rewrite_report.txt / .json as the research generator wrote them (text mode on Windows)."""
    write_text(os.path.join(dst_dir, REPORT_TXT), '\n'.join(lines) + '\n', 'utf-8')
    write_json(os.path.join(dst_dir, REPORT_JSON), rep_json)


# ============================================================================================== the stage
def load_api(research=None):
    """the two engines' registered script functions (research/scripts/xml{1,2}_api.json: packaged data)."""
    research = Path(research) if research else REPO_ROOT / 'research'
    return [json.loads((research / rel).read_text(encoding='utf-8')) for rel in API_RELS]


def stage_key(disc_stage: dict, tables_dir: Path, research: Path) -> str:
    tables_dir = Path(tables_dir)
    inputs = {'mission_plan': sha1_file(tables_dir / 'mission_plan.json'),
              'missions': {f.name: sha1_file(f) for f in sorted((tables_dir / P2.MISSIONS_DIR).glob('*.xml'))},
              'api': {rel: sha1_file(research / rel) for rel in API_RELS}}
    return digest({'stage': STAGE, 'version': VERSION, 'disc': disc_stage.get('key'), 'inputs': inputs})


def run(disc_dir, tables_dir, *, research=None, log=print, cancel=None, force=False) -> dict:
    """P3 from a published P1 directory + a published P2 directory; reuses the published output while its key
    matches. Returns {'dir', 'stage', 'cached'}; the build reads <dir>/out as research scripts/out."""
    t0 = time.time()
    disc_dir, tables_dir = Path(disc_dir), Path(tables_dir)
    research = Path(research) if research else REPO_ROOT / 'research'
    dst = read_stage(disc_dir)
    if not dst or dst.get('stage') != P1.STAGE:
        raise RuntimeError(f'{disc_dir} is not a published P1 disc directory')
    tst = read_stage(tables_dir)
    if not tst or tst.get('stage') != P2.STAGE:
        raise RuntimeError(f'{tables_dir} is not a published P2 tables directory')
    key = stage_key(dst, tables_dir, research)
    final = disc_dir.parent / 'prepared' / f'{STAGE}-v{VERSION}-{key[:12]}'
    st = read_stage(final)
    if st and st.get('key') == key and not force:
        log(f'[prepare] scripts: cached ({final})')
        return {'dir': final, 'stage': st, 'cached': True}
    partial = final.with_name(final.name + '.partial')
    rmtree(partial)
    partial.mkdir(parents=True)
    api1, api2 = load_api(research)
    plan = json.loads((tables_dir / 'mission_plan.json').read_text(encoding='latin-1'))
    t = time.time()
    rw = Rewriter(disc_dir / P1.LOOSE, disc_dir / P1.ASSETS, plan, api1, api2, cancel=cancel)
    t_analyse = round(time.time() - t, 1)
    t = time.time()
    lines, rep_json, counts = rw.write(str(partial / OUT), missions_src=tables_dir / P2.MISSIONS_DIR)
    write_report(partial, lines, rep_json)
    counts['files'] = sum(len(fs) for _, _, fs in os.walk(partial / OUT))
    stage = {'stage': STAGE, 'version': VERSION, 'key': key, 'disc_key': dst.get('key'),
             'tables_key': tst.get('key'), 'counts': counts,
             'timings': {'analyse': t_analyse, 'write': round(time.time() - t, 1)},
             'seconds': round(time.time() - t0, 1)}
    stage = publish(partial, final, stage)
    log(f'[prepare] scripts: done in {stage["seconds"]}s: {counts}')
    for old in final.parent.glob(f'{STAGE}-v*'):
        if old != final and not old.name.endswith('.partial'):
            rmtree(old)
    return {'dir': final, 'stage': stage, 'cached': False}
