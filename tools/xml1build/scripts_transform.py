"""xml1build.scripts_transform - text transforms the scripts module applies to the research scripts it installs.

The research output (research/scripts/out/scripts, rewrite_scripts.py) is installed as-is except for these
deterministic, verifiable post-passes (scripts.py _script_text):

1. narrow_packed(lines, specs): give chosen packed XML1 mission counters their real bit width.
   rewrite_scripts.py stores every XML1 mission var that is set from a variable as an 8-bit field of an x1v##
   game var (COUNTER_BITS = 8), read and written one bit at a time: a read costs 1 + 3*(n-1) statements (+4 for
   the sign extension of a signed var), a variable write 1 + 5n - 1 (+4), a literal write n. The XML2 script
   engine has one global pool of 620 statement nodes (0x4d7e6e) per loaded zone script set; mastermold2 needed
   907 (research scripts VERIFICATION: 'corecount' core_on/off 23 -> 83 lines each). Narrowing a var from n to
   k bits deletes the bit terms / bit groups / literal bits k..n-1 in place and rescales the sign-extension
   constants (2^(n-1) -> 2^(k-1), 2^n -> 2^k). The storage layout (game var, first bit) is unchanged; the high
   bits are simply never read or written again (they are still cleared at mission start by nothing: every
   clear of them is removed too, and no reader is left - checked). Every literal written must fit k bits
   (checked). Blocks are matched exactly in rewrite_scripts.gen_get / gen_set / gen_clear's format; a reference
   to a narrowed bit outside a recognised block is a problem (the script is then left unchanged).
2. normalise_zone_literals(text): SPEC 4.1 - the zone literal of loadZone / loadMapKeepTeam / loadMapChooseTeam /
   loadMapAddTeam / loadMap / restorelastzone (also inside blackbirdMenu's stored code) and both paths of
   cinematicStart (subtitle, cancel script) become lowercase '/' paths (C.norm).
3. blackbird_to_choose_team(text): optional fallback (build option --blackbird chooseteam):
   blackbirdMenu(a, "loadMapKeepTeam('z')", b) -> loadMapChooseTeam("z" ). XML2 retail never calls
   blackbirdMenu from a script; loadMapChooseTeam is what XML2's own new_game_hard.py uses.
4. rename_mission_anims(text): XML1 plays mission / briefing animations through the enum names EA_MISSION1..20
   (default.xbe 'ea_mission1'; XML1 data/shared_anims.xml ea_missionN = 'missionN'). XMen2.exe has no ea_mission*
   enum (no 'ea_mission1' string); its equivalent is ea_zone1..20 (string 0x683170; XML2 Data/shared_anims.XMLB
   ea_zoneN = 'zoneN'). EA_MISSIONn -> EA_ZONEn (case kept, n = 1..20), and the anim-name literal 'missionN' of
   setCombatNode / loopCombatNode -> 'zoneN'; the characters module renames the 'missionN' anims inside the 43
   XML1 mission_* anim DBs to 'zoneN' to match. Also applied to data trees (scripts.rewrite_data_tree).
5. choose_team_in_bodies(lines, bodies): a mission start (the inlined body of an XML1 beginMission, marked
   '# ( "XML1 beginMission(m)" )') of a mission whose XML1 data forces heroes (REQUIREDHERO or maxheros < 4) loads
   its zone with loadMapChooseTeam instead of loadMapKeepTeam, so the player can at least match the party
   (retail XML2 has no script function that adds or removes a party member; without xml2-fix [Game] ForcedTeams
   this is the port's behaviour, and in --forced-teams seat builds it is the else branch of 7).
6. inject_act(lines, act): setCurrentAct(n) as the first statement (after the leading comments), in
   rewrite_scripts' own injection format.
7. Forced teams (SPEC 19, research/heroes/FORCED_TEAMS_DESIGN.md 3): forced_party_in_bodies (every begin body:
   the seat block of a forced mission, the skinset block of the others), side_push_at_markers /
   side_push_before_marker (XML1 beginSideMission -> pushParty), side_end_at_markers (XML1 endSideMission ->
   popParty, else the team menu), join_hero(add_hero=True) (the addHero branch, then joinHero, before the T7
   fallback). Every
   xml2-fix call sits in the 'then' branch of 'if <v> == 1' where <v> was declared with iadd(0, 0 ) and assigned
   from xml2fixFeature(...): without the DLL the xml2fixFeature line is dropped at compile (an unregistered name
   drops only its own statement, 0x4da37a), <v> stays 0 and the else branch runs: the team menu at forced starts
   (as before SPEC 19), and at side-mission returns, which used to loadZone(caller) with the flashback party
   (roster T9's simplest variant, SPEC 19.1); the joins keep their T7 block.
   xml2fix_guard_problems(lines) checks that rule (scripts lint, validate V14b).

run_pack_ops(lines, flags, env) is a tiny interpreter of the statements these transforms touch (assignments from
getGameFlag / iadd / isub / imul / idiv, setGameFlag, if/elif/else/endif on integer comparisons; every other
call returns 0); selftest() uses it to prove narrowed blocks round-trip every value of their range.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass

from . import common as C

LOAD_ZONE_FUNCS = ('loadZone', 'loadMapKeepTeam', 'loadMapChooseTeam', 'loadMapAddTeam', 'loadMap',
                   'restorelastzone')
SIGN_COMMENT = '# ( "x1 sign-extend" )'


def _norm(p):
    s = str(p).replace('\\', '/')
    while s.startswith('./'):
        s = s[2:]
    return s.lstrip('/').lower()


def _canon(line):
    return re.sub(r'\s+', ' ', line.strip())


def _call(name, *args):
    return f'{name}({", ".join(str(a) for a in args)} )' if args else f'{name}( )'


@dataclass(frozen=True)
class NarrowSpec:
    key: str          # var_storage.json key ('m:corecount')
    g: str            # game var ('x1v05')
    b: int            # first (least significant) bit, 1-based as in setGameFlag
    n: int            # current width
    k: int            # new width
    signed: bool

    @property
    def high(self):
        return range(self.b + self.k, self.b + self.n)

    def fits(self, v):
        if self.signed:
            return -(1 << (self.k - 1)) <= v < (1 << (self.k - 1))
        return 0 <= v < (1 << self.k)


_FLAG_RE = re.compile(r'''(get|set)GameFlag\(\s*(["'])(\w+)\2\s*,\s*(\d+)\s*(?:,\s*([^)]*?))?\s*\)''')


def narrow_packed(lines, specs):
    """Narrow the packed vars in `specs` (list of NarrowSpec) in a script given as a list of lines (no line
    ends). Returns (new_lines, changes Counter, problems list). On any problem the lines are returned unchanged."""
    by_g = collections.defaultdict(list)
    for sp in specs:
        by_g[sp.g].append(sp)

    def spec_of(g, bit):
        for sp in by_g.get(g, ()):
            if sp.b <= bit < sp.b + sp.n:
                return sp
        return None

    drop = set()
    repl = {}
    changes = collections.Counter()
    problems = []
    handled = set()                   # line indices that belong to a recognised block
    n_lines = len(lines)
    c = [_canon(l) for l in lines]
    i = 0
    while i < n_lines:
        # ---------------------------------------------------------------- read block (gen_get)
        m = re.fullmatch(r'''(\w+) = getGameFlag\(\s*(["'])(\w+)\2\s*,\s*(\d+)\s*\)''', c[i])
        if m and m.group(1) != 'x1_b':
            V, q, g, bit = m.group(1), m.group(2), m.group(3), int(m.group(4))
            sp = spec_of(g, bit)
            if sp is not None and bit == sp.b:
                j = i + 1
                ok = True
                triples = []
                for bb in range(sp.b + 1, sp.b + sp.n):
                    exp = [f'x1_b = getGameFlag({q}{g}{q}, {bb} )', f'x1_b = imul(x1_b, {1 << (bb - sp.b)} )',
                           f'{V} = iadd({V}, x1_b )']
                    if j + 3 > n_lines or [_canon(x) for x in exp] != c[j:j + 3]:
                        ok = False
                        break
                    triples.append((bb, j))
                    j += 3
                sign = None
                if ok and sp.signed:
                    exp = [SIGN_COMMENT, f'if {V} >= {1 << (sp.n - 1)}', f'{V} = isub({V}, {1 << sp.n} )', 'endif']
                    if [_canon(x) for x in exp] == c[j:j + 4]:
                        sign = j
                        j += 4
                    else:
                        ok = False
                if ok:
                    for idx in range(i, j):
                        handled.add(idx)
                    for bb, t in triples:
                        if bb >= sp.b + sp.k:
                            drop.update((t, t + 1, t + 2))
                    if sign is not None:
                        repl[sign + 1] = lines[sign + 1].replace(f'>= {1 << (sp.n - 1)}', f'>= {1 << (sp.k - 1)}')
                        repl[sign + 2] = lines[sign + 2].replace(f', {1 << sp.n} )', f', {1 << sp.k} )')
                    changes[f'read:{sp.key}'] += 1
                    i = j
                    continue
        # ---------------------------------------------------------------- variable write block (gen_set)
        m = re.fullmatch(r'x1_t = iadd\((.+), 0 \)', c[i])
        if m and m.group(1).strip() != 'x1_q':
            j = i + 1
            sign = None
            if c[j:j + 4] and c[j] == SIGN_COMMENT and j + 4 <= n_lines:
                m2 = re.fullmatch(r'if x1_t < 0', c[j + 1])
                m3 = re.fullmatch(r'x1_t = iadd\(x1_t, (\d+) \)', c[j + 2])
                if m2 and m3 and c[j + 3] == 'endif':
                    sign = (j, int(m3.group(1)))
                    j += 4
            groups = []
            g = q = None
            while j + 4 <= n_lines:
                pre = None
                if groups:
                    if c[j] != 'x1_t = iadd(x1_q, 0 )':
                        break
                    pre = j
                    j += 1
                m4 = re.fullmatch(r'''setGameFlag\((["'])(\w+)\1, (\d+), x1_r \)''', c[j + 3]) if j + 3 < n_lines else None
                if not (c[j] == 'x1_q = idiv(x1_t, 2 )' and c[j + 1] == 'x1_r = imul(x1_q, 2 )' and
                        c[j + 2] == 'x1_r = isub(x1_t, x1_r )' and m4):
                    if pre is not None:
                        j -= 1
                    break
                if g is None:
                    q, g = m4.group(1), m4.group(2)
                elif m4.group(2) != g:
                    if pre is not None:
                        j -= 1
                    break
                groups.append((int(m4.group(3)), pre, j))
                j += 4
            if groups:
                sp = spec_of(g, groups[0][0])
                bits = [bb for bb, _, _ in groups]
                if sp is not None and bits == list(range(sp.b, sp.b + sp.n)) and \
                        (sign is not None) == sp.signed and (sign is None or sign[1] == 1 << sp.n):
                    for idx in range(i, j):
                        handled.add(idx)
                    for bb, pre, t in groups:
                        if bb >= sp.b + sp.k:
                            if pre is not None:
                                drop.add(pre)
                            drop.update(range(t, t + 4))
                    if sign is not None:
                        repl[sign[0] + 2] = lines[sign[0] + 2].replace(f', {1 << sp.n} )', f', {1 << sp.k} )')
                    changes[f'write:{sp.key}'] += 1
                    i = j
                    continue
        # ---------------------------------------------------------------- literal writes / clears (runs)
        m = re.fullmatch(r'''setGameFlag\((["'])(\w+)\1, (\d+), (-?\d+) \)''', c[i])
        if m:
            j = i
            run = []
            while j < n_lines:
                mm = re.fullmatch(r'''setGameFlag\((["'])(\w+)\1, (\d+), (-?\d+) \)''', c[j])
                if not mm:
                    break
                run.append((j, mm.group(2), int(mm.group(3)), int(mm.group(4))))
                j += 1
            per = collections.defaultdict(dict)
            for idx, g, bb, val in run:
                sp = spec_of(g, bb)
                if sp is not None:
                    per[sp][bb] = (idx, val)
            for sp, bits in per.items():
                if sorted(bits) != list(range(sp.b, sp.b + sp.n)):
                    continue                  # not a whole-var write: left for the leftover check below
                v = sum((1 << (bb - sp.b)) for bb, (_, val) in bits.items() if val)
                if sp.signed and v >= 1 << (sp.n - 1):
                    v -= 1 << sp.n
                if not sp.fits(v):
                    problems.append(f'line {bits[sp.b][0] + 1}: literal {v} does not fit {sp.k} bits of {sp.key}')
                    continue
                for bb, (idx, _) in bits.items():
                    handled.add(idx)
                    if bb >= sp.b + sp.k:
                        drop.add(idx)
                changes[f'literal:{sp.key}'] += 1
            i = j
            continue
        i += 1
    # every reference to a narrowed high bit must be inside a recognised (and therefore rewritten) block
    for idx, line in enumerate(lines):
        for mm in _FLAG_RE.finditer(line):
            sp = spec_of(mm.group(3), int(mm.group(4)))
            if sp is not None and idx not in handled:
                problems.append(f'line {idx + 1}: {mm.group(0)} touches narrowed {sp.key} outside a recognised '
                                f'rewrite_scripts block')
    if problems:
        return list(lines), collections.Counter(), problems
    new = [repl.get(idx, line) for idx, line in enumerate(lines) if idx not in drop]
    return new, changes, []


# ------------------------------------------------------------------------------------------------ zone literals
_ZONE_CALL = re.compile(r'''\b(?P<fn>%s)\s*\(\s*(?P<q>["'])(?P<z>[^"'()]*)(?P=q)''' % '|'.join(LOAD_ZONE_FUNCS))
_CINE = re.compile(r'''\bcinematicStart\s*\(\s*(?P<q1>["'])(?P<a>[^"']*)(?P=q1)\s*,\s*(?P<q2>["'])(?P<b>[^"']*)(?P=q2)''')


def normalise_zone_literals(text):
    """-> (text, [(old, new)]) with every zone/path literal named in the module doc normalised (C.norm)."""
    changed = []

    def zsub(m):
        z = m.group('z')
        nz = _norm(z)
        if nz == z:
            return m.group(0)
        changed.append((z, nz))
        s, e = m.span('z')
        return m.group(0)[:s - m.start()] + nz + m.group(0)[e - m.start():]

    text = _ZONE_CALL.sub(zsub, text)

    def csub(m):
        out = m.group(0)
        for grp in ('b', 'a'):                     # right to left keeps the spans valid
            v = m.group(grp)
            nv = _norm(v)
            if nv != v:
                changed.append((v, nv))
                s, e = m.span(grp)
                out = out[:s - m.start()] + nv + out[e - m.start():]
        return out

    text = _CINE.sub(csub, text)
    return text, changed


# ------------------------------------------------------------------------------------------------ blackbird
_BB = re.compile(r'''^(?P<ind>\s*)blackbirdMenu\(\s*"[^"]*"\s*,\s*"loadMapKeepTeam\('(?P<z>[^'"()]+)'\)"\s*,\s*"[^"]*"\s*\)\s*$''')


def blackbird_to_choose_team(lines):
    """-> (lines, [zone]) with every blackbirdMenu(a, "loadMapKeepTeam('z')", b) line replaced by
    loadMapChooseTeam("z" ) (same indentation)."""
    out, zones = [], []
    for line in lines:
        m = _BB.match(line)
        if m:
            zones.append(m.group('z'))
            out.append(f'{m.group("ind")}loadMapChooseTeam("{m.group("z")}" )')
        else:
            out.append(line)
    return out, zones


# ------------------------------------------------------------------------------------------------ mission anims
MISSION_ANIM_MAX = 20            # XML1 ea_mission1..20, XML2 ea_zone1..20
_EA_MISSION = re.compile(r'(?i)\b(?P<ea>ea_)(?P<m>mission)(?P<n>\d+)\b')
_COMBAT_NODE_MISSION = re.compile(r'''(?P<pre>\b(?:set|loop)CombatNode\s*\(\s*(?P<q>["'])[^"']*(?P=q)\s*,\s*(?P<q2>["']))'''
                                  r'''(?P<m>mission)(?P<n>\d+)(?P=q2)''', re.I)


def _zone_word(m):
    return 'ZONE' if m.isupper() else ('zone' if m.islower() else 'Zone')


def rename_mission_anims(text):
    """-> (text, [(old, new)]): EA_MISSIONn -> EA_ZONEn and (set|loop)CombatNode(..., "missionN") -> "zoneN" for
    n = 1..MISSION_ANIM_MAX (case kept). Any other n is left alone (XML1 has none)."""
    changed = []

    def esub(m):
        n = int(m.group('n'))
        if not 1 <= n <= MISSION_ANIM_MAX:
            return m.group(0)
        new = f'{m.group("ea")}{_zone_word(m.group("m"))}{m.group("n")}'
        changed.append((m.group(0), new))
        return new

    def csub(m):
        n = int(m.group('n'))
        if not 1 <= n <= MISSION_ANIM_MAX:
            return m.group(0)
        old = m.group('m') + m.group('n')
        new = _zone_word(m.group('m')) + m.group('n')
        changed.append((old, new))
        return f'{m.group("pre")}{new}{m.group("q2")}'

    text = _EA_MISSION.sub(esub, text)
    text = _COMBAT_NODE_MISSION.sub(csub, text)
    return text, changed


# ---------------------------------------------------------------------- unwakeable LOOP_WAKE loops (npc-loop fix)
# XML1 spawn scripts loop an animation with playanim(<EA_*>, "_OWNER_", "LOOP_WAKE", "") and rely on the NPC's AI
# to end ("wake") it: the riot looters (nyc/riots/prep_smash_down, prep_jump_smash, prep_smash_side[_pipe]) swing a
# baseball bat until the player comes within their fleedistance and they flee; the Weapon X lab techs work at their
# consoles until they are disturbed. XMen2.exe keeps the loop mode in the entity at +0x388 (playanim handler
# 0x4a8a20: STOP=1, LOOP=2, LOOP_WAKE=3 from the table at 0x68a880; the play routine 0x430d40 restarts the node
# while the mode is 2 or 3) and ends a LOOP_WAKE in exactly two places, both inside the combat AI: 0x5100d0 (after
# a target was acquired in 0x514080) and 0x513ff3 (the alert scan 0x513c50). Neither runs for a non-combatant:
# the attack decision 0x514080 returns unless the team is hero/enemy/altenemy (0x41a220 != 0x1c) and willflee is
# not set (cmp byte [ai+0x46d],1 at 0x51410c), the default brain 0x51dfe0 leaves before its targeting block for
# team none, and XMen2.exe has no flee behaviour at all: the AI's fleedistance (+0x470, filled at 0x5034d2) is
# never read by AI code and willflee (+0x46d) is only tested at 0x507925 / 0x50e5ef / 0x51240a / 0x51410c, every
# one of them a gate that suppresses attacking (XML2 retail ships no willflee stats and one spawner with
# monster_willflee="false"). A missing team is team none (stats default 0x1c at 0x4bce9b; 0x45fbd0 maps only
# hero/enemy/altenemy). So a LOOP_WAKE on such an NPC never ends: the looters "attack" forever.
#
# Fix, in XML2's own spawn-script idiom (12 XML2 spawnscripts play an anim, waittimed(), then act; inline data
# code uses the same statements separated by INLINE_SEP): the loop is bounded to UNWAKEABLE_LOOP_SECONDS and then
# stopped with the STOP mode of the same call (node gen_anim_stop, 0x693de4), after which the NPC idles. Only a
# statement that is the last one of its script is rewritten (the wait would delay anything after it).
UNWAKEABLE_LOOP_SECONDS = 15.0
UNWAKEABLE_COMMENT = '# ( "x1: bounded LOOP_WAKE - XMen2.exe wakes a loop only from its combat AI, which never runs ' \
                     'for a team-none / willflee NPC (no flee AI)" )'
_PLAYANIM_LOOP_WAKE = re.compile(
    r'''^(?P<ind>\s*)(?P<head>playanim\s*\(\s*(?P<q1>["'])(?P<anim>[^"']+)(?P=q1)\s*,\s*(?P<q2>["'])_owner_(?P=q2)'''
    r'''\s*,\s*(?P<q3>["']))(?P<mode>loop_wake)(?P<tail>(?P=q3)\s*,\s*(?P<q4>["'])[^"']*(?P=q4)\s*\)\s*)$''', re.I)
_COMMENT_OR_BLANK = re.compile(r'^\s*(#.*)?$')


def bound_unwakeable_loops(statements, seconds=UNWAKEABLE_LOOP_SECONDS, inline=False):
    """statements: the lines of a script file (inline=False) or the INLINE_SEP-separated statements of one inline
    data value (inline=True). Every `playanim(<anim>, "_OWNER_", "LOOP_WAKE", <x>)` that is the last statement
    becomes LOOP + waittimed(seconds) + the same call with STOP. -> (statements, [(anim, index)], [(anim, index)
    skipped because a statement follows])."""
    out, changed, skipped = [], [], []
    last = max((i for i, s in enumerate(statements) if not _COMMENT_OR_BLANK.match(s)), default=-1)
    for i, s in enumerate(statements):
        m = _PLAYANIM_LOOP_WAKE.match(s)
        if m is None:
            out.append(s)
            continue
        if i != last:
            skipped.append((m.group('anim'), i))
            out.append(s)
            continue
        ind = m.group('ind')
        loop = f'{ind}{m.group("head")}LOOP{m.group("tail")}'
        stop = f'{ind}{m.group("head")}STOP{m.group("tail")}'
        if inline:
            out += [loop, f'waittimed({seconds:g})', stop.strip()]
        else:
            out += [loop, f'{ind}{UNWAKEABLE_COMMENT}', f'{ind}waittimed ( {seconds:.3f} )', stop]
        changed.append((m.group('anim'), i))
    return out, changed, skipped


# ------------------------------------------------------------------------------------------------ forced heroes
BEGIN_MARKER = re.compile(r'''^\s*#\s*\(\s*"XML1 beginMission\((?P<m>[^)"]+)\)"\s*\)\s*$''')
_KEEP_TEAM = re.compile(r'''^(?P<ind>\s*)loadMapKeepTeam(?P<rest>\s*\(.*)$''')


def choose_team_in_bodies(lines, bodies):
    """-> (lines, [(mission, line text)]). bodies: {mission: [stripped body lines, marker first]} of the missions
    that force heroes. Every occurrence of such a body (the marker line followed by the body's statements, compared
    stripped) gets its loadMapKeepTeam(...) statements replaced by loadMapChooseTeam(...) (same arguments and
    indentation). Nested bodies are covered by the outer span and by their own entry. Without xml2-fix [Game]
    ForcedTeams the team menu is all the port can do; forced_party_in_bodies then wraps this load into the seat
    block, whose else branch it stays."""
    out = list(lines)
    changed = []
    strip = [l.strip() for l in out]
    for i, s in enumerate(strip):
        m = BEGIN_MARKER.match(s)
        if not m:
            continue
        body = bodies.get(m.group('m').strip().lower())
        if not body or strip[i:i + len(body)] != body:
            continue
        for j in range(i, i + len(body)):
            k = _KEEP_TEAM.match(out[j])
            if k:
                out[j] = f'{k.group("ind")}loadMapChooseTeam{k.group("rest")}'
                changed.append((m.group('m').lower(), out[j].strip()))
    return out, changed


# ------------------------------------------------------------------------------------------------ forced teams
# xml2-fix script functions (FORCED_TEAMS_DESIGN.md 1.2; research/scripts/xml2fix_api.json is the versioned copy
# the build merges into the API of --forced-teams seat builds): name -> (ret, args)
XML2FIX_API = {'xml2fixFeature': ('i', 's'), 'seatParty': ('n', 'ssss'), 'setSkinset': ('n', 'ss'),
               'pushParty': ('n', 'a'), 'popParty': ('n', 's'), 'addHero': ('i', 's'), 'getPartyMember': ('s', 'i'),
               'joinHero': ('i', 's'), 'addSkillPoints': ('n', 'ai')}
# xml2-fix functions data may call directly (SPEC 32: the SKILL item's onactivate): not forced-teams features, registered
# with the rest whatever [Game] ForcedTeams says, inert without the DLL (the engine drops a call it doesn't know)
XML2FIX_DATA_FUNCS = frozenset(C.XML2FIX_ALWAYS_FUNCS)
FT_VAR, AH_VAR, JH_VAR = 'x1ft', 'x1ah', 'x1jh'
FT_FEATURE, AH_FEATURE, JH_FEATURE = 'forcedteams', 'addhero', 'joinhero'
FEATURES = (FT_FEATURE, AH_FEATURE, JH_FEATURE)
# the function each xml2-fix call needs switched on (the 'then' branch of 'if <v> == 1', <v> = xml2fixFeature(f))
GUARD_OF = {'seatParty': FT_FEATURE, 'setSkinset': FT_FEATURE, 'pushParty': FT_FEATURE, 'popParty': FT_FEATURE,
            'addHero': AH_FEATURE, 'getPartyMember': None, 'joinHero': JH_FEATURE}
IND = '     '                                  # BehavEd's block indentation
# a no-op (0x5aaff0) that keeps a branch non-empty when the DLL is absent and its xml2-fix calls are dropped at compile
# (XML2 retail scripts never have an empty block; research rewrite_scripts keeps blocks non-empty the same way)
FT_KEEP = 'debug("x1: xml2-fix forced teams" )'
FT_SEAT_COMMENT = '# ( "x1: XML1 forces this party (xml2-fix [Game] ForcedTeams); without it the team menu opens" )'
FT_SKIN_COMMENT = '# ( "x1: XML1 mission skinset (xml2-fix [Game] ForcedTeams)" )'
FT_PUSH_COMMENT = '# ( "x1: XML1 beginSideMission saves zone, party and spot (xml2-fix pushParty)" )'
FT_POP_COMMENT = ('# ( "x1: XML1 endSideMission restores the saved party and spot (xml2-fix popParty); without it '
                  'the team menu opens" )')
FT_T9_COMMENT = '# ( "x1: endSideMission - the team menu at the caller zone (T9, no party record for this side mission)" )'
SIDE_BEGIN_MARKER = re.compile(r'''^\s*#\s*\(\s*"XML1 beginSideMission\((?P<s>[^)"]+)\)''')
SIDE_END_MARKER = re.compile(r'''^\s*#\s*\(\s*"XML1 endSideMission from side mission (?P<s>[^"\s]+)"\s*\)\s*$''')
_LOAD_STMT = re.compile(r'''^(?P<ind>\s*)(?P<fn>loadMapKeepTeam|loadMapChooseTeam|loadZone)\(\s*"(?P<z>[^"]*)"''')
_BB_STMT = re.compile(r'''^(?P<ind>\s*)blackbirdMenu\(\s*"[^"]*"\s*,\s*"loadMapKeepTeam\('(?P<z>[^'"()]+)'\)"''')
_SET_ACT = re.compile(r'^\s*setCurrentAct\s*\(\s*\d+\s*\)\s*$')
_LOAD_ZONE_EMPTY = re.compile(r'''^(?P<ind>\s*)loadZone\(\s*"(?P<z>[^"]+)"\s*,\s*""\s*\)\s*$''')


def feature_detect(var, feature, ind=''):
    """the declaration (retail idiom, act1/codes_convo_1.py) + the feature query. An undeclared variable would drop
    the 'if' line itself (script-functions 7.3); a declared one stays 0 when the query line is dropped."""
    return [f'{ind}{var} = iadd(0, 0 )', f'{ind}{var} = xml2fixFeature("{feature}" )']


def seat_party_call(seat):
    names = list(seat)[:4]
    names += [''] * (4 - len(names))
    return 'seatParty(' + ', '.join(f'"{n}"' for n in names) + ' )'


def set_skinset_call(costume, heroes):
    return f'setSkinset("{costume}", "{heroes}" )'


def seat_block(ind, seat, costume, heroes, zone):
    """the forced-mission start (design 3.2): seat + skinset + loadMapKeepTeam, else loadMapChooseTeam."""
    return [ind + FT_SEAT_COMMENT] + feature_detect(FT_VAR, FT_FEATURE, ind) + [
        f'{ind}if {FT_VAR} == 1', ind + IND + seat_party_call(seat), ind + IND + set_skinset_call(costume, heroes),
        f'{ind}{IND}loadMapKeepTeam("{zone}" )', f'{ind}else', f'{ind}{IND}loadMapChooseTeam("{zone}" )', f'{ind}endif']


def skinset_block(ind, costume, heroes):
    """a free (or unseatable / cut) mission start: only the mission skinset, before its load (design 3.5)."""
    return [ind + FT_SKIN_COMMENT] + feature_detect(FT_VAR, FT_FEATURE, ind) + [
        f'{ind}if {FT_VAR} == 1', ind + IND + FT_KEEP, ind + IND + set_skinset_call(costume, heroes), f'{ind}endif']


def push_block(ind=''):
    """XML1 beginSideMission, half 1 (design 3.4): the record is pushed before the side mission's seatParty."""
    return [ind + FT_PUSH_COMMENT] + feature_detect(FT_VAR, FT_FEATURE, ind) + [
        f'{ind}if {FT_VAR} == 1', ind + IND + FT_KEEP, f'{ind}{IND}pushParty("_ACTIVE_HERO_" )', f'{ind}endif']


def pop_block(ind, costume, heroes, zone):
    """XML1 endSideMission (design 3.4): the caller mission's skinset + popParty (restorelastzone 0, or the team
    menu at `zone` when no record is on the stack); without the feature the team menu at `zone` (T9 simple)."""
    return [ind + FT_POP_COMMENT] + feature_detect(FT_VAR, FT_FEATURE, ind) + [
        f'{ind}if {FT_VAR} == 1', ind + IND + FT_KEEP, ind + IND + set_skinset_call(costume, heroes),
        f'{ind}{IND}popParty("{zone}" )', f'{ind}else', f'{ind}{IND}loadMapChooseTeam("{zone}" )', f'{ind}endif']


def body_load_index(body):
    """index of the body's final load statement (loadMapKeepTeam / loadMapChooseTeam / loadZone / blackbirdMenu)
    in a list of lines, or None."""
    for j in range(len(body) - 1, -1, -1):
        if _LOAD_STMT.match(body[j]) or _BB_STMT.match(body[j]):
            return j
    return None


def body_load(line):
    """(function, zone) of a load statement line, or (None, None)."""
    m = _LOAD_STMT.match(line)
    if m:
        return m.group('fn'), m.group('z')
    m = _BB_STMT.match(line)
    if m:
        return 'blackbirdMenu', m.group('z')
    return None, None


def forced_party_in_bodies(lines, bodies, plan):
    """-> (lines, [(mission, kind, zone)]). bodies: {mission: stripped body lines, marker first} as they are after
    choose_team_in_bodies; plan: {mission: {'status', 'seat', 'costume', 'heroes'}}. Every occurrence of a body
    (marker + exactly its statements, compared stripped) gets, at its final load statement:
      status 'seat'       the load (loadMapKeepTeam / loadMapChooseTeam "z") replaced by seat_block;
      any other status    skinset_block inserted before the load (blackbirdMenu / loadMapKeepTeam / ...).
    An occurrence already rewritten no longer matches its body, so the pass is idempotent."""
    strip = [l.strip() for l in lines]
    edits = []                                       # (index, remove_count, new_lines, record)
    for i, s in enumerate(strip):
        m = BEGIN_MARKER.match(s)
        if not m:
            continue
        mis = m.group('m').strip().lower()
        body, p = bodies.get(mis), plan.get(mis)
        if not body or p is None or strip[i:i + len(body)] != body:
            continue
        k = body_load_index(lines[i:i + len(body)])
        if k is None:
            continue
        j = i + k
        fn, zone = body_load(lines[j])
        ind = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
        if p.get('status') == 'seat' and fn in ('loadMapKeepTeam', 'loadMapChooseTeam') and p.get('seat'):
            edits.append((j, 1, seat_block(ind, p['seat'], p['costume'], p['heroes'], zone), (mis, 'seat', zone)))
        else:
            edits.append((j, 0, skinset_block(ind, p['costume'], p['heroes']), (mis, 'skinset', zone)))
    out = list(lines)
    done = []
    for j, n, new, rec in sorted(edits, key=lambda e: -e[0]):
        out[j:j + n] = new
        done.append(rec)
    return out, sorted(done)


def side_push_at_markers(lines, sides):
    """-> (lines, [side]): push_block after every '# ( "XML1 beginSideMission(s) ..." )' marker of a side mission
    in `sides` (script begin sites, design 3.4); idempotent.
    A movie before the marker (astral/savepx/xcrystal_destroyed: startMovie("r504") + waitsignal, then the marker)
    takes the push ahead of it: while the movie's menu is up there is no _ACTIVE_HERO_ to push (in game 2026-09-28:
    "pushParty: no entity by that name - nothing pushed"), and loadsentinel's push-then-movie order is the one
    verified in game. The hero doesn't move during the movie, so the saved spot is the same."""
    out, done = [], []
    for i, l in enumerate(lines):
        out.append(l)
        m = SIDE_BEGIN_MARKER.match(l)
        if not m or m.group('s').strip().lower() not in sides:
            continue
        if (i + 1 < len(lines) and lines[i + 1].strip() == FT_PUSH_COMMENT) or \
                any(x.strip() == FT_PUSH_COMMENT for x in out[:-1]):
            continue
        ind = l[:len(l) - len(l.lstrip())]
        movie = next((j for j, x in enumerate(out[:-1])
                      if _MOVIE_START.match(x) and x[:len(x) - len(x.lstrip())] == ind), None)
        if movie is not None:
            out[movie:movie] = push_block(ind)
        else:
            out += push_block(ind)
        done.append(m.group('s').strip().lower())
    return out, done


_MOVIE_START = re.compile(r'^\s*startMovie\s*\(')


def side_push_before_marker(lines, side):
    """-> (lines, inserted?): push_block before the first '# ( "XML1 beginMission(side)" )' marker (the begin script
    of a side mission only a data beginSideMission starts: conversation chosenscriptfile); idempotent."""
    n = len(push_block())
    for i, l in enumerate(lines):
        m = BEGIN_MARKER.match(l.strip())
        if m and m.group('m').strip().lower() == side:
            if any(x.strip() == FT_PUSH_COMMENT for x in lines[max(0, i - n):i]):
                return list(lines), False
            ind = l[:len(l) - len(l.lstrip())]
            return list(lines[:i]) + push_block(ind) + list(lines[i:]), True
    return list(lines), False


def side_end_at_markers(lines, ends):
    """-> (lines, [(side, zone, kind)], [problem]). ends: {side: (costume, heroes) for popParty, or None for the
    team menu only (T9 simple)}. At every '# ( "XML1 endSideMission from side mission s" )' marker of a side in
    `ends` the generated loadZone("<caller>", "" ) after it (an optional setCurrentAct stays) becomes pop_block
    (or loadMapChooseTeam). A marker without that loadZone is a problem. Idempotent."""
    out = list(lines)
    edits, done, probs = [], [], []
    for i, l in enumerate(lines):
        m = SIDE_END_MARKER.match(l)
        if not m:
            continue
        side = m.group('s').strip().lower()
        if side not in ends:
            continue
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith('#') or _SET_ACT.match(lines[j])):
            j += 1
        if j < len(lines) and lines[j].strip() in (FT_POP_COMMENT, FT_T9_COMMENT):
            continue                                                            # already rewritten
        z = _LOAD_ZONE_EMPTY.match(lines[j]) if j < len(lines) else None
        if z is None:
            probs.append(f'line {i + 1}: endSideMission({side}) marker without the generated loadZone("<caller>", "" )')
            continue
        ind, zone = z.group('ind'), z.group('z')
        spec = ends[side]
        if spec is None:
            new = [ind + FT_T9_COMMENT, f'{ind}loadMapChooseTeam("{zone}" )']
            kind = 'menu'
        else:
            new = pop_block(ind, spec[0], spec[1], zone)
            kind = 'pop'
        edits.append((j, new))
        done.append((side, zone, kind))
    for j, new in sorted(edits, key=lambda e: -e[0]):
        out[j:j + 1] = new
    return out, done, probs


_ASSIGN_CALL = re.compile(r'^(?P<v>[A-Za-z_]\w*)\s*=(?!=)\s*(?P<fn>[A-Za-z_][\w.]*)\s*\((?P<args>.*)\)\s*$')
_BARE_CALL = re.compile(r'^(?P<fn>[A-Za-z_][\w.]*)\s*\((?P<args>.*)\)\s*$')
_GUARD_IF = re.compile(r'^if\s+(?P<v>[A-Za-z_]\w*)\s*==\s*1\s*:?\s*$')


def _strip_comment(line):
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in '"\'':
            q = ch
        elif ch == '#':
            return line[:i]
    return line


def xml2fix_guard_problems(lines, funcs=XML2FIX_API):
    """[(lineno, problem)] for xml2-fix calls that would run without their feature switched on (validate V14b):
    every call of `funcs` must sit in the 'then' branch of 'if <v> == 1' where <v> was declared with
    '<v> = iadd(0, 0 )' and then assigned '<v> = xml2fixFeature("forcedteams"|"addhero" )' earlier in the same
    script; seatParty / setSkinset / pushParty / popParty need the forcedteams guard, addHero the addhero guard
    (its own assignment 'x1ah = addHero(...)' included), joinHero the joinhero guard. xml2fixFeature itself is only
    valid as that assignment.
    Without the DLL the query line is dropped, <v> stays 0 and the branch never runs; an undeclared <v> would drop
    the 'if' line itself and run the branch unconditionally."""
    probs = []
    decl = {}                                  # var -> declared by iadd(0, 0 ) (True) / other assignment (False)
    feat = {}                                  # var -> feature it currently holds
    stack = []                                 # [guard feature or None, in_then]
    for no, raw in enumerate(lines, 1):
        s = _strip_comment(raw).strip()
        if not s:
            continue
        first = re.split(r'[\s(:]', s, 1)[0].lower()
        if first == 'if':
            m = _GUARD_IF.match(s)
            g = feat.get(m.group('v').lower()) if m else None
            stack.append([g, True])
            continue
        if first in ('elif', 'elseif', 'else'):
            if stack:
                stack[-1][1] = False
            continue
        if first == 'endif':
            if stack:
                stack.pop()
            continue
        active = {g for g, then in stack if then and g}
        m = _ASSIGN_CALL.match(s)
        if m:
            v, fn, args = m.group('v').lower(), m.group('fn'), m.group('args')
            fn = fn[5:] if fn.lower().startswith('game.') else fn
            if fn == 'iadd' and re.fullmatch(r'\s*0\s*,\s*0\s*', args):
                decl[v], feat[v] = True, None
                continue
            if fn == 'xml2fixFeature':
                lit = re.fullmatch(r'\s*"([^"]*)"\s*', args)
                f = lit.group(1) if lit else None
                if f not in FEATURES:
                    probs.append((no, f'xml2fixFeature({args.strip()}): feature must be one of {FEATURES}'))
                if not decl.get(v):
                    probs.append((no, f'{v} = xml2fixFeature(...): {v} is not declared with {v} = iadd(0, 0 ) '
                                      f'before (without the DLL the if line would be dropped)'))
                feat[v] = f if decl.get(v) else None
                continue
            decl[v], feat[v] = False, None
        else:
            m = _BARE_CALL.match(s)
            if not m:
                continue
            fn = m.group('fn')
            fn = fn[5:] if fn.lower().startswith('game.') else fn
            if fn == 'xml2fixFeature':
                probs.append((no, 'xml2fixFeature(...) must be assigned to a declared variable'))
                continue
        if fn in funcs and fn != 'xml2fixFeature':
            need = GUARD_OF.get(fn)
            if need is None:
                if not active:
                    probs.append((no, f'{fn}(): not inside an "if <v> == 1" xml2fixFeature guard'))
            elif need not in active:
                probs.append((no, f'{fn}(): not inside an "if <v> == 1" guard of xml2fixFeature("{need}")'))
    return probs


# ------------------------------------------------------------------------------------------------ act on entry
ACT_COMMENT = '# ( "x1: load this act\'s objectives on zone entry (XML2 zone scripts do the same)" )'


def first_statement_act(lines):
    """the literal act of a setCurrentAct that is the first statement, else None."""
    for l in lines:
        s = l.strip()
        if not s or s.startswith('#'):
            continue
        m = re.fullmatch(r'setCurrentAct\s*\(\s*(\d+)\s*\)', s)
        return int(m.group(1)) if m else None
    return None


def inject_act(lines, act):
    """-> lines with ACT_COMMENT + setCurrentAct(act ) inserted before the first statement (rewrite_scripts.py's
    format: after the leading blank/comment lines)."""
    k = 0
    while k < len(lines) and (not lines[k].strip() or lines[k].lstrip().startswith('#')):
        k += 1
    return list(lines[:k]) + [ACT_COMMENT, _call('setCurrentAct', int(act))] + list(lines[k:])


# ------------------------------------------------------------------------------------------------ join hero (T7)
# XML1 addHero("cyclops") (nyc/alison/add_cyclops, mansion/dr_mag2/blob/add_cyclops) was rewritten by the research
# as unlockCharacter x2 + extractionPointLite("_ACTIVE_HERO_", ...). XMen2.exe's extractionPointLite (0x4a6d80)
# shows only the hint dialog dialogs/xpoint_lite_hint and returns while game flag danv bit 1 is clear (0x4a6e3e-
# 0x4a6e63), which in a fresh game it always is: Cyclops never joined. XML2 has no seat-a-hero call (the party slot
# writer 0x46c810 is not scriptable); extractionPointChange (0x4a7020) pushes the position, opens the team menu and
# reloads the zone at the same spot with the chosen party (research/heroes/roster.md T7). The reload re-arms the
# trigger and respawns the NPC, so the zone script clears them while the x1join bit is set; the bit is cleared at
# the owning mission's start. Seat builds try xml2-fix joinHero first (SPEC 19.7): the same save-spot-and-reload
# with the hero added to the saved party, no team menu. XML1's join popup (nyc: dialogs/tut15) must not be pending
# across the reload or the team menu (in game 2026-09-28: created 2 s after the trigger, it sat invisible UNDER the
# team menu and broke its buttons - the likeliest cause of Owen's pad-B hang; shown from the reloaded zone's script
# it fired under the loading screen and was lost), so it comes first, with a waittimed after it: the wait runs out
# only once the player has closed it (the game pauses), then the join (in game, the same night).
JOIN_FLAG = 'x1join'
JOIN_COMMENT = ('# ( "x1 addHero(%s): XML2 has no seat-a-hero call (0x46c810 is not scriptable); save the spot and '
                'open the team menu" )')
JOIN_GUARD_COMMENT = '# ( "x1: after addHero the zone reloads: drop the re-armed join trigger and the NPC double" )'
# The NPC double's own name. The join zones' spawner spawns the hero as an NPC named after the hero, and XML2 names
# the party's heroes after their herostat entry too; remove(name) removes EVERY entity of that name (0x4a9300 ->
# 0x4a7e30), so after the join's reload remove("cyclops") took the party's Cyclops along with the double (in game,
# 2026-09-28), and without it the double stood next to him. zones.py renames the double (the spawner's
# monster_name; JOIN_DOUBLE_SPAWNERS) and the join script and zone guard remove it by that name - XML2's own
# pattern (tutorial1's Cyclops NPC is "simplecyclops").
JOIN_DOUBLE_SPAWNERS = {'nyc/alison/nyc1_1_3': ('sp_cyclops01', 'cyclops'),
                        'mansion/dr_mag2/mag_nyc4': ('sp_cyclops01', 'cyclops')}


def join_double(hero):
    return f'{hero.lower()}_x1double'


# The other same-name NPCs (SPEC 18; FORCED_TEAMS_DESIGN 5). A zone that spawns an NPC named after a playable hero,
# where a script addresses that name and the party CAN hold that hero, gets the same treatment as the join doubles:
# the spawner's monster_name becomes join_double(hero) (zones.rename_npc_doubles) and the entity references of the
# zone's scripts follow (rename_npc_refs). Evidence, 2026-09-28 (every other case is in HERO_NPC_REVIEW):
#   mocap1/briefing_1_1_6_5: nyc/alison/blackbird_brief1 loadZone()s it straight from alison, so the party is
#     Wolverine (+ Cyclops after the join); the briefing's own playanim("EA_ZONEn", "wolverine" / "cyclops") lines
#     address its mocap NPCs by those names (the begin body of mansion1 that seats Magma runs only after it).
#   mocap4/briefing_1_7_1: sewers/quest/fadegambit loadMapKeepTeam()s it, so the party is whatever the player picked
#     for the sewers (free mission): any of the heroes below, Gambit too once the profile has him (below).
#   muir_is/muir2/muir_in2 (2026-09-28): muir2 seats Magma, but with [Game] ForcedTeams=0 (or without xml2-fix) its
#     start opens the team menu, and Storm there lost her party slot to 2_4_1_cleanup's remove("storm"); Cyclops
#     (faceEntity) and Colossus (setEnable / copyOriginAndAngles, a spawnscript) likewise once picked.
#   nuke_plant/nuke/nuke2_2, nyc/riots/nyc3_1_2, sewers/hub/sewers1_2_4 (2026-09-28): free parties. Colossus /
#     Psylocke are unlocked only at mansion4 / mansion7 and Gambit by fadegambit in that very zone, but XMen2.exe
#     keeps unlocks in the PROFILE (settings.dat), not in the game: unlockCharacter sets the registry bit AND the
#     profile bit (0x449c00 -> profile vt+0x28 0x48f740, the bitset at profile+0x1c0), New Game's resetgame clears
#     only the registry bits (0x449540, from 0x5f2f96), and the team menu's pick checks the profile bit (vt+0x38
#     0x48f770 at 0x5e3d81 / 0x5e5319 / 0x5e55cb) - the same reason XML2's shared profile offered the port every hero
#     before [Game] SaveFolder. So from the second New Game on (or after any restart past the unlock) the hero can be
#     picked for these zones; colossus_holding's playanim(... "colossus", "LOOP") would loop the party's Colossus,
#     fadegambit's fade/remove("gambit") would take the party's Gambit, conv3_2_3 would move the party's Psylocke.
# The briefings run as cinematics with subtitles (no conversation speaker lines), so the renamed NPCs lose nothing.
# The other zones' doubles speak: their conversations follow (NPC_DOUBLE_CONVERSATIONS, rename_speaker_tokens) and
# the double's name gets a speaker stats entry (NPC_DOUBLE_SPEAKERS), so the talk animation still finds the NPC.
NPC_DOUBLE_SPAWNERS = {
    'mocap/mocap1/briefing_1_1_6_5': {'sp_wolverinemocap': 'wolverine', 'sp_cyclopsmocap': 'cyclops'},
    'mocap/mocap4/briefing_1_7_1': {'sp_wolverinemocap': 'wolverine', 'sp_cyclopsmocap': 'cyclops',
                                    'sp_roguemocap': 'rogue', 'sp_phoenixmocap': 'phoenix', 'sp_stormmocap': 'storm',
                                    'sp_nightcrawlermocap': 'nightcrawler', 'sp_gambitmocap01': 'gambit'},
    'muir_is/muir2/muir_in2': {'sp_colossus01': 'colossus', 'sp_cyclops01': 'cyclops', 'sp_stormscripted01': 'storm'},
    'nuke_plant/nuke/nuke2_2': {'sp_colossus01': 'colossus'},
    'nyc/riots/nyc3_1_2': {'psy_spawn': 'psylocke'},
    'sewers/hub/sewers1_2_4': {'sp_gambit01': 'gambit'},
}
# script ref -> the zone whose doubles its entity references mean (every script that addresses them runs only there:
# the zone's package lists it, or a conversation / spawner of that zone runs it)
NPC_DOUBLE_SCRIPTS = {'mocap/mocap1/briefing_1_1_6_5': 'mocap/mocap1/briefing_1_1_6_5',
                      'mocap/mocap4/briefing_1_7_1': 'mocap/mocap4/briefing_1_7_1',
                      'muir_is/muir2/2_4_1_cleanup': 'muir_is/muir2/muir_in2',        # conversation 2_4_1
                      'muir_is/muir2/cyclops_face_alison': 'muir_is/muir2/muir_in2',  # conversation 2_4_6
                      'nuke_plant/nuke/colossus_holding': 'nuke_plant/nuke/nuke2_2',  # sp_colossus01 spawnscript
                      'nyc/riots/conv3_2_3': 'nyc/riots/nyc3_1_2',
                      'sewers/quest/fadegambit': 'sewers/hub/sewers1_2_4',            # conversation 1_5_5
                      'sewers/quest/gambit_spawn': 'sewers/hub/sewers1_2_4',          # sp_gambit01 spawnscript
                      'sewers/quest/gambit_free': 'sewers/hub/sewers1_2_4'}           # conversation 1_5_5
# conversation ref -> the zone whose doubles speak in it (each is precached / packaged by that zone only; validate V6
# checks it): %HERO% speaker tokens of that zone's doubles become %HERO_X1DOUBLE% (the talk animation goes to the
# zone entity with the speaker key's name, 0x45bd1e -> 0x4c6f20; the name label and portrait come from the stats
# entry of that name, 0x456d00 / 0x5f4ec0), and its inline code follows rename_npc_refs.
NPC_DOUBLE_CONVERSATIONS = {'muir_is/muir2/2_4_1': 'muir_is/muir2/muir_in2', 'muir_is/muir2/2_4_3': 'muir_is/muir2/muir_in2',
                            'muir_is/muir2/2_4_6': 'muir_is/muir2/muir_in2', 'muir_is/muir2/2_4_11': 'muir_is/muir2/muir_in2',
                            'muir_is/muir2/2_4_11b': 'muir_is/muir2/muir_in2',
                            'nuke_plant/nuke/2_3_3': 'nuke_plant/nuke/nuke2_2', 'nuke_plant/nuke/2_3_4': 'nuke_plant/nuke/nuke2_2',
                            'nyc/riots/3_2_3': 'nyc/riots/nyc3_1_2',
                            'sewers/quest/1_5_3': 'sewers/hub/sewers1_2_4', 'sewers/quest/1_5_5': 'sewers/hub/sewers1_2_4'}
# heroes whose double speaks in NPC_DOUBLE_CONVERSATIONS: heroes.py adds an npcstat entry join_double(hero) (the
# hero's charactername / skin / characteranims, team none, never spawned) so %HERO_X1DOUBLE% shows the hero's name and
# portrait. Storm has no line in muir_in2.
NPC_DOUBLE_SPEAKERS = ('colossus', 'cyclops', 'gambit', 'psylocke')
# Hero NPCs that keep XML1's own entity name and speak under the hero's token (SPEC 18.1, 2026-09-29). The joins'
# Cyclops lines, line by line: the join zones themselves (nyc1_1_3, mag_nyc4) have ONE Cyclops speaker line,
# nyc1_1_3's 1_1_5_1d, and it plays after the join (HERO_SPEAKER_REVIEW 'party'); the lines Cyclops speaks as an NPC
# come one zone earlier, in nyc1_1_2b (alison) and its Danger Room copy mag_nyc3 (dr_mag2): there Mystique, disguised
# as Cyclops, is the spawner NPC "cyclops_scripted" (character cyclops; cyc_wp2 morphs it into Mystique) and says
# 1_1_09 "Hey, Wolverine." / 2_2_1_0_5 "All right." under %CYCLOPS%. That token's talk animation goes to the entity
# named "cyclops" (0x45bd1e -> 0x4c6f20, a case-folded name lookup, 0x5602b0): nobody there (alison seats Wolverine,
# dr_mag2 Magma; Cyclops joins in the next zone), so the NPC stood still. Its lines now name the NPC
# (%CYCLOPS_SCRIPTED%) and a speaker stats entry of that name shows Cyclops's name and portrait (speaker_stats_entries).
# The same for the NPC Alison and the NPC Emma (2026-09-29, line by line from XML1's scripts):
#   * nyc1_1_3 (alison): the NPC "alison" (sp_magma01, character magma, skin 1803, team none) punches the Blob
#     (alison_gets_away: playanim EA_ATTACK_LIGHT1 on "alison") and says 1_1_5_1b (her cry for help), then
#     runs to alison_spot (alison_gets_away_2); the party is Wolverine + Cyclops. XML1 wrote %ALISON%, which the port
#     turns into %MAGMA% (scripts.SPEAKER_TOKEN_ALIASES) - no entity "magma" there, so she stood still.
#   * mag_nyc4 (dr_mag2, the Danger Room replay with Magma in the party): the simulated Alison "alison_scripted" says the
#     same line, 2_2_1_3b (2_2_1_3a_end: she punches the Blob, then startConversation 2_2_1_3b), and the party Magma
#     would have mouthed it. The zone's other %ALISON% lines are Magma's own (HERO_SPEAKER_REVIEW 'party' below).
#   * mansion4_1 (mansion4, Magma forced): Emma Frost is the NPC "emma" (sp_frost01, character frost; her actscript
#     starts 2_5_10, emma_talk / profx_apears start 2_5_10b, every %FROST% line hers). Magma's lines there keep %MAGMA%.
# conversation ref -> (the zone that packages it, {hero: the NPC entity that speaks the hero's lines there})
NPC_SPEAKER_CONVERSATIONS = {
    'nyc/alison/1_1_09': ('nyc/alison/nyc1_1_2b', {'cyclops': 'cyclops_scripted'}),
    'mansion/dr_mag2/2_2_1_0_5': ('mansion/dr_mag2/mag_nyc3', {'cyclops': 'cyclops_scripted'}),
    'nyc/alison/1_1_5_1b': ('nyc/alison/nyc1_1_3', {'magma': 'alison'}),
    'mansion/dr_mag2/2_2_1_3b': ('mansion/dr_mag2/mag_nyc4', {'magma': 'alison_scripted'}),
    'mansion/man4/2_5_10': ('mansion/man4/mansion4_1', {'frost': 'emma'}),
    'mansion/man4/2_5_10b': ('mansion/man4/mansion4_1', {'frost': 'emma'}),
}
# Speaker entries whose name label is not the hero's charactername. default.xbe labels every %ALISON% line with its
# string 503 "Alison" (0x61c81-0x61c8f: string table vt+8(0x1f7), data/strings.eng id 503, the same in .fre/.ger) and
# keys the speaker to the stats entry Magma (0x61bf0-0x61c24: registry vt+0x3c("Magma") -> vt+0x68 -> its name), so
# XML1 showed "Alison" with Magma's portrait. XMen2.exe labels a line with its stats entry's charactername (0x456d00,
# 0x425bc0), so the NPC Alison's speaker entries carry "Alison" and Magma's skin (portrait) - XML1's label and portrait.
SPEAKER_DISPLAY_NAMES = {'alison': 'Alison', 'alison_scripted': 'Alison'}


def speaker_stats_entries():
    """{stats name: hero}: the speaker-only npcstat entries heroes.py adds (the hero's charactername / skin /
    characteranims - the charactername SPEAKER_DISPLAY_NAMES' where it has one - team none, never spawned):
    join_double(h) for NPC_DOUBLE_SPEAKERS and the NPC names of NPC_SPEAKER_CONVERSATIONS."""
    out = {join_double(h): h for h in NPC_DOUBLE_SPEAKERS}
    for _zone, speakers in NPC_SPEAKER_CONVERSATIONS.values():
        for h, npc in speakers.items():
            out[npc.lower()] = h.lower()
    return out


# V6 speaker review (SPEC 18.1): a conversation line under a playable hero's %HERO% token, packaged by a zone that
# spawns an NPC of that hero under another entity name - the NPC stands there, but the talk animation goes to the
# entity named HERO (the party's hero). Each such (conversation, hero) is renamed above or reviewed here:
#   party  only the party's hero can speak it there (the zone flow puts it after the hero's join, or the party hero
#          is the speaker)
#   open   the NPC speaks it and keeps the hero's token for now: name label and portrait right, no talk animation
#          (validate V6 warns; the fix is NPC_SPEAKER_CONVERSATIONS' - token + speaker entry of the NPC's name)
HERO_SPEAKER_REVIEW_REASONS = ('party', 'open')
HERO_SPEAKER_REVIEW = {
    # nyc1_1_3 (the alison join zone): the Blob scene (trigger_touch01 alison_gets_away -> 1_1_5_1b ->
    # alison_gets_away_2 -> 1_1_5_1d -> 1_1_5_1_end) comes after the join: from the entry start the zone's nav mesh
    # reaches the Blob trigger only across the join trigger trigger_touch03 (add_cyclops; without its cells 72 of
    # 2072 cells are reachable), and XML1's scene puts _HERO2_ on cyc_spot and wakes "cyclops" - the party Cyclops.
    ('nyc/alison/1_1_5_1d', 'cyclops'): 'party',
    # mag_nyc4 (dr_mag2's join zone; alison_scripted is the Danger Room's simulated Alison): Magma is the party hero
    ('mansion/dr_mag2/2_2_1_3_new', 'magma'): 'party',     # Magma recalls Cyclops's words (to the Blob)
    ('mansion/dr_mag2/2_2_1_3a', 'magma'): 'party',        # "Hey, that's me!" (notalkanim)
    ('mansion/dr_mag2/2_2_2', 'magma'): 'party',           # Magma's victory line
    # (no 'open' entry left: the Alison and Emma lines are renamed above, 2026-09-29. nyc/alison/blackbird packages
    # 1_1_6_5, Jean's NPC "jeangray" under %PHOENIX%, but no load reaches that zone)
}
# Reviewed same-name NPCs that keep the hero's name (zone -> {hero: reason}); validate V6 (_v6_hero_npcs) makes any
# other reachable zone whose scripts address a hero-named NPC an error until it is renamed or reviewed here, and
# accepts only HERO_NPC_REVIEW_REASONS.
#   forced   every way into the zone seats a party without that hero (SPEC 19 seat blocks / popParty; the party a
#            save there holds is that party). With [Game] ForcedTeams=0 the team menu could add the hero (SPEC 18.1
#            "open with ForcedTeams=0"; muir_in2 is renamed instead).
#   party    the zone is entered with one known party that lacks the hero (mocap1: alison's Wolverine + Cyclops)
# "The hero is not unlocked yet" is no reason (2026-09-28): the profile keeps unlocks from game to game (see above).
HERO_NPC_REVIEW_REASONS = ('forced', 'party')
HERO_NPC_FORCED_ZONES = (
    'mansion/man1a/mansion1a_1', 'mansion/man1a/mansion1a_2', 'mansion/man2/mansion2_1', 'mansion/man3/hangar3',
    'mansion/man3/mansion3_1', 'mansion/man3/subbasement3b', 'mansion/man4/mansion4_1', 'mansion/man4/subbasement4',
    'mansion/man6/subbasement6', 'mansion/man7/mansion7_1', 'mansion/man7/status_meeting', 'mansion/man7/subbasement7',
    'mocap/mocap2/briefing_1_2_41', 'mocap/mocap3/briefing_1_4_13', 'mocap/mocap5/briefing_2_1_16',
    'mocap/mocap6/briefing_2_5_5', 'mocap/mocap7/briefing_2_5_14_7', 'mocap/mocap8/briefing_2_5_22',
    'mocap/mocap9/briefing_3_1_8', 'mocap/mocap10/briefing_3_6_6', 'mocap/mocap11/briefing_3_6_7',
    'mocap/mocap12/briefing_3_9_0', 'mocap/mocap13/briefing_3_9_8')
HERO_NPC_REVIEW = {z: {'*': 'forced'} for z in HERO_NPC_FORCED_ZONES}
HERO_NPC_REVIEW.update({
    'mocap/mocap1/briefing_1_1_6_5': {h: 'party' for h in ('beast', 'colossus', 'iceman', 'phoenix', 'storm')},
})
# calls whose string arguments name no entity (a hero / objective / flag / skinset name): skipped when looking for
# the scripts that address an NPC by name
NON_ENTITY_CALLS = frozenset({'unlockCharacter', 'isCharacterUnlocked', 'seatParty', 'setSkinset', 'addHero', 'joinHero',
                              'objective', 'getObjective', 'immediateObjective', 'disallowResponseOnObjective',
                              'debug', 'setGameFlag', 'getGameFlag'})
_CALL_ARGS = re.compile(r'\b(?P<fn>[A-Za-z_]\w*)\s*\((?P<args>[^()]*)\)')
_STR_LIT = re.compile(r'''(?P<q>["'])(?P<v>[^"']*)(?P=q)''')


def entity_name_refs(line, names):
    """[(function, name)]: the string arguments of the calls in one statement (or inline code) that equal one of
    `names` (lowercase set), outside NON_ENTITY_CALLS. Comments are ignored."""
    s = line.strip()
    if not s or s.startswith('#'):
        return []
    out = []
    for m in _CALL_ARGS.finditer(s):
        if m.group('fn') in NON_ENTITY_CALLS:
            continue
        for lit in _STR_LIT.finditer(m.group('args')):
            if lit.group('v').lower() in names:
                out.append((m.group('fn'), lit.group('v').lower()))
    return out


def rename_npc_refs(lines, heroes):
    """-> (lines, n): every string argument naming one of `heroes` in an entity call (entity_name_refs) becomes
    join_double(hero), the renamed NPC (NPC_DOUBLE_SPAWNERS). Idempotent (the double's name is no hero name)."""
    names = {h.lower() for h in heroes}
    out, n = [], 0

    def sub_call(m):
        nonlocal n
        if m.group('fn') in NON_ENTITY_CALLS:
            return m.group(0)

        def sub_lit(lit):
            nonlocal n
            if lit.group('v').lower() not in names:
                return lit.group(0)
            n += 1
            return f'{lit.group("q")}{join_double(lit.group("v"))}{lit.group("q")}'
        return m.group(0)[:m.start('args') - m.start()] + _STR_LIT.sub(sub_lit, m.group('args')) + \
            m.group(0)[m.end('args') - m.start():]
    for l in lines:
        s = l.strip()
        out.append(l if not s or s.startswith('#') else _CALL_ARGS.sub(sub_call, l))
    return out, n


def double_speaker_token(hero):
    """the conversation speaker token of a renamed NPC double: '%CYCLOPS_X1DOUBLE%' (XML1's upper-case style; the
    stats lookup ignores case)."""
    return f'%{join_double(hero).upper()}%'


_SPEAKER = re.compile(r'%(?P<n>[^%\s]+)%')


def rename_speaker_tokens(text, heroes):
    """-> (text, n): conversation text/textb whose %HERO% speaker token (any case) names one of `heroes` gets the
    double's token (double_speaker_token) - or, `heroes` a mapping {hero: npc name}, the token %NPC NAME%
    (NPC_SPEAKER_CONVERSATIONS). Idempotent."""
    names = {h.lower(): v for h, v in heroes.items()} if isinstance(heroes, dict) else {h.lower(): None for h in heroes}
    n = 0

    def sub(m):
        nonlocal n
        key = m.group('n').lower()
        if key not in names:
            return m.group(0)
        n += 1
        return f'%{names[key].upper()}%' if names[key] else double_speaker_token(m.group('n'))
    return _SPEAKER.sub(sub, text), n


def npc_double_conversation_heroes(conv_ref):
    """the heroes whose doubles speak in conversation `conv_ref` ('muir_is/muir2/2_4_1'; NPC_DOUBLE_CONVERSATIONS),
    empty when the conversation is not one of them."""
    zone = NPC_DOUBLE_CONVERSATIONS.get((conv_ref or '').lower())
    return set(NPC_DOUBLE_SPAWNERS[zone].values()) if zone else set()


def npc_speaker_renames(conv_ref):
    """{hero: npc name} of conversation `conv_ref` ('nyc/alison/1_1_09'; NPC_SPEAKER_CONVERSATIONS), empty when the
    conversation is not one of them."""
    spec = NPC_SPEAKER_CONVERSATIONS.get((conv_ref or '').lower())
    return {h.lower(): npc.lower() for h, npc in spec[1].items()} if spec else {}
JOIN_RESET_COMMENT = '# ( "x1: mission start clears the addHero join bit" )'
_UNLOCK = re.compile(r'''^(?P<ind>\s*)unlockCharacter\(\s*"(?P<hero>\w+)"\s*,\s*""\s*\)\s*$''')
_XPL = re.compile(r'''^(?P<ind>\s*)extractionPointLite\(\s*"_ACTIVE_HERO_"\s*,.*\)\s*$''')
_TAIL = re.compile(r'^\s*(waittimed\s*\(|createPopupDialogXml\s*\()')
_POPUP = re.compile(r'''^\s*createPopupDialogXml\s*\(\s*"(?P<xml>[^"]+)"\s*\)\s*$''')
_WAITTIMED = re.compile(r'^\s*waittimed\s*\(')


JOIN_ADDHERO_COMMENT = ('# ( "x1 addHero(%s): xml2-fix addHero seats the hero on the NPC\'s spot without a reload '
                        '([Game] AddHero=1, experimental); otherwise the T7 fallback below" )')
JOIN_JOINHERO_COMMENT = ('# ( "x1 joinHero(%s): xml2-fix saves the spot, adds the hero to the saved party and reloads '
                         'the zone there - no team menu ([Game] JoinHero, on with ForcedTeams=1)" )')
JOIN_POPUP_COMMENT = ('# ( "x1: the join popup first - the wait after it runs out only once the player has closed it '
                      '(the game pauses), so the reload / team menu comes after it" )')
JOIN_POPUP_WAIT = '0.500'                         # verified in game 2026-09-28 night (build/_jh, main session)
JOIN_LATE_COMMENT = ('# ( "x1: the spawner\'s instant spawn comes after the zone script\'s removes: remove the NPC '
                     'double again as it appears (the zone script\'s waits run from the loading screen on)" )')
# the waits between the late removes of the double (s; cumulative 0.25 .. 10.5): the double appears when the load is
# done, which takes a varying time after the zone script starts, and a remove of an absent entity does nothing
JOIN_LATE_REMOVE_WAITS = ('0.250', '0.250', '0.500', '0.500', '0.500', '0.500', '1.000', '1.000', '2.000', '4.000')


def join_block(ind, hero, bit, add_hero=False):
    """T7 (add_hero False): unlock, comment, remove the double, set the join bit, extractionPointChange.
    With add_hero (design 3.6, --forced-teams seat): the join bit is set first, then xml2-fix addHero(hero) when
    xml2fixFeature("addhero") is on (the double is removed AFTER it: the hero takes the NPC's spot), then xml2-fix
    joinHero(hero) when addHero did not seat him and xml2fixFeature("joinhero") is on (the double removed BEFORE
    it: the reload respawns the zone, the zone guard removes the respawned double), and the T7 block runs when
    both are off, the DLL absent, or both returned 0 (joinHero: 1 = the reload is queued, 2 = in the party already,
    0 = refused). joinHero queues the reload (restorelastzone 0), so it is the last statement of its branch and the
    only console command of the run (V14f)."""
    d = join_double(hero)
    rm = f'remove ( "{d}", "{d}" )'
    if not add_hero:
        return [f'{ind}unlockCharacter("{hero}", "" )', f'{ind}{JOIN_COMMENT % hero}', f'{ind}{rm}',
                f'{ind}setGameFlag("{JOIN_FLAG}", {int(bit)}, 1 )', f'{ind}extractionPointChange("_ACTIVE_HERO_", 0 )']
    return [f'{ind}unlockCharacter("{hero}", "" )', f'{ind}setGameFlag("{JOIN_FLAG}", {int(bit)}, 1 )',
            f'{ind}{JOIN_ADDHERO_COMMENT % hero}'] + feature_detect(AH_VAR, AH_FEATURE, ind) + [
            f'{ind}if {AH_VAR} == 1', f'{ind}{IND}{AH_VAR} = addHero("{hero}" )', f'{ind}{IND}{rm}', f'{ind}endif',
            f'{ind}{JOIN_JOINHERO_COMMENT % hero}', f'{ind}{JH_VAR} = iadd(0, 0 )',
            f'{ind}if {AH_VAR} == 0', f'{ind}{IND}{FT_KEEP}', f'{ind}{IND}{JH_VAR} = xml2fixFeature("{JH_FEATURE}" )',
            f'{ind}endif',
            f'{ind}if {JH_VAR} == 1', f'{ind}{IND}{rm}', f'{ind}{IND}{AH_VAR} = joinHero("{hero}" )', f'{ind}endif',
            f'{ind}if {AH_VAR} == 0', f'{ind}{IND}{JOIN_COMMENT % hero}', f'{ind}{IND}{rm}',
            f'{ind}{IND}extractionPointChange("_ACTIVE_HERO_", 0 )', f'{ind}endif']


def join_hero(lines, bit, add_hero=False):
    """-> (lines, [hero], [popup xml]) with every unlockCharacter("h", "") x N + extractionPointLite(
    "_ACTIVE_HERO_", ...) run replaced by join_block: unlockCharacter once, the join comment, remove(join_double(h))
    (the NPC double spawned by the zone's spawner, renamed by zones.py), setGameFlag("x1join", bit, 1) and
    extractionPointChange("_ACTIVE_HERO_", 0) - with add_hero the xml2-fix addHero and joinHero branches first
    (join_block). The waittimed / createPopupDialogXml lines that followed move before the block (the reload kills
    the script), and every popup gets a waittimed right after it: the wait does not run out while the popup is up
    (the game pauses; in game 2026-09-28 night the next statement ran 0.4 s after the popup was closed), so the
    reload or the team menu only comes once the player has closed it. A popup still up under the team menu broke the
    menu (in game, the same day), and one up across the reload was lost."""
    out = list(lines)
    heroes, popups = [], []
    i = 0
    while i < len(out):
        m = _XPL.match(out[i])
        if not m:
            i += 1
            continue
        j = i
        hero = None
        while j > 0 and _UNLOCK.match(out[j - 1]):
            hero = _UNLOCK.match(out[j - 1]).group('hero')
            j -= 1
        if hero is None:
            i += 1
            continue
        k = i + 1
        tail = []
        while k < len(out) and _TAIL.match(out[k]):
            tail.append(out[k])
            k += 1
        ind = m.group('ind')
        moved = []
        for n, t in enumerate(tail):
            p = _POPUP.match(t)
            if p:
                popups.append(p.group('xml'))
                moved.append(f'{ind}{JOIN_POPUP_COMMENT}')
            moved.append(t)
            if p and not (n + 1 < len(tail) and _WAITTIMED.match(tail[n + 1])):
                moved.append(f'{ind}waittimed ( {JOIN_POPUP_WAIT} )')
        block = moved + join_block(ind, hero, bit, add_hero)
        out[j:k] = block
        heroes.append(hero)
        i = j + len(block)
    return out, heroes, popups


def join_hero_zone_guard(lines, bit, entities=('trigger_touch03', 'sp_cyclops01', join_double('cyclops')),
                         late=(join_double('cyclops'),)):
    """-> (lines, inserted?) the zone-script guard (after a leading setCurrentAct, else before the first
    statement), idempotent. The spawner instant-spawns the double AFTER the zone script's removes (in game
    2026-09-28 night: bit set, the guard ran, the double still stood there; a remove sent after the load cleared
    him), so the end of the zone script (its waits delay nothing else) removes `late` again, after each wait of
    JOIN_LATE_REMOVE_WAITS."""
    out, ins = list(lines), False
    if not any(JOIN_GUARD_COMMENT in l for l in out):
        guard = [JOIN_GUARD_COMMENT, f'x1j = getGameFlag("{JOIN_FLAG}", {int(bit)} )', 'if x1j == 1'] + \
                [f'     remove ( "{e}", "{e}" )' for e in entities] + ['endif']
        k = 0
        while k < len(out) and (not out[k].strip() or out[k].lstrip().startswith('#')):
            k += 1
        if k < len(out) and re.fullmatch(r'setCurrentAct\s*\(\s*\d+\s*\)', out[k].strip()):
            k += 1
        out, ins = out[:k] + guard + out[k:], True
    if late and not any(JOIN_LATE_COMMENT in l for l in out):
        block = [JOIN_LATE_COMMENT, 'if x1j == 1']
        for w in JOIN_LATE_REMOVE_WAITS:
            block += [f'{IND}waittimed ( {w} )'] + [f'{IND}remove ( "{e}", "{e}" )' for e in late]
        block.append('endif')
        end = len(out)
        while end > 0 and out[end - 1] == '':
            end -= 1                                           # before the final CRLF
        out, ins = out[:end] + block + out[end:], True
    return out, ins


def join_hero_mission_reset(lines, bits):
    """-> (lines, [(mission, bit)]): setGameFlag("x1join", bit, 0) right after every '# ( "XML1 beginMission(m)" )'
    marker of a mission in bits ({mission: bit}); idempotent."""
    out, done = [], []
    for i, l in enumerate(lines):
        out.append(l)
        m = BEGIN_MARKER.match(l.strip())
        if not m:
            continue
        mis = m.group('m').strip().lower()
        if mis not in bits:
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ''
        if nxt == JOIN_RESET_COMMENT:
            continue
        ind = l[:len(l) - len(l.lstrip())]
        out += [f'{ind}{JOIN_RESET_COMMENT}', f'{ind}setGameFlag("{JOIN_FLAG}", {int(bits[mis])}, 0 )']
        done.append((mis, bits[mis]))
    return out, done


# ------------------------------------------------------------------------------------------------ team lock
# XML1's Xtraction team change kept a mission's REQUIRED heroes and maxheros; XMen2.exe's Xtraction menu offers
# Change Team anywhere, and its team menu lets every player (online: a player on standby too) pick any unlocked
# hero (research/online/online_forced_parties.md). xml2-fix f06f2e2+ greys Change Team out while game flag
# "teamlock" bit 1 is set ([Game] ForcedTeams=1): every mission start sets it - 1 for a seated forced mission,
# 0 for every other - and a side mission's return (popParty) sets its caller mission's value. A game flag is saved
# with the game and streamed to joiners with the host's save, so every machine greys the same option.
TEAM_LOCK_FLAG, TEAM_LOCK_BIT = 'teamlock', 1
TEAM_LOCK_COMMENT = '# ( "x1: XML1 keeps a forced mission\'s party at its Xtraction Points (xml2-fix teamlock)" )'
TEAM_LOCK_RETURN_COMMENT = '# ( "x1: back in the caller mission - its team lock (xml2-fix teamlock)" )'


def team_lock_line(value, ind=''):
    return f'{ind}setGameFlag("{TEAM_LOCK_FLAG}", {TEAM_LOCK_BIT}, {1 if value else 0} )'


def team_lock_at_markers(lines, values):
    """-> (lines, [(mission, value)]): TEAM_LOCK_COMMENT + setGameFlag("teamlock", 1, v) right after every
    '# ( "XML1 beginMission(m)" )' marker of a mission in values ({mission: 0/1}); idempotent."""
    out, done = [], []
    for i, l in enumerate(lines):
        out.append(l)
        m = BEGIN_MARKER.match(l.strip())
        if not m:
            continue
        mis = m.group('m').strip().lower()
        if mis not in values:
            continue
        if i + 1 < len(lines) and lines[i + 1].strip() == TEAM_LOCK_COMMENT:
            continue
        ind = l[:len(l) - len(l.lstrip())]
        out += [ind + TEAM_LOCK_COMMENT, team_lock_line(values[mis], ind)]
        done.append((mis, int(bool(values[mis]))))
    return out, done


def team_lock_at_side_ends(lines, values):
    """-> (lines, [(side, value)]): TEAM_LOCK_RETURN_COMMENT + setGameFlag("teamlock", 1, v) right before every
    '# ( "XML1 endSideMission from side mission s" )' marker of a side in values ({side: the caller mission's
    0/1}), at the marker's indentation (the same branch; the marker and the pop after it stay together);
    idempotent."""
    out, done = [], []
    for i, l in enumerate(lines):
        m = SIDE_END_MARKER.match(l)
        side = m.group('s').strip().lower() if m else None
        if side in values and not (i >= 2 and lines[i - 2].strip() == TEAM_LOCK_RETURN_COMMENT):
            ind = l[:len(l) - len(l.lstrip())]
            out += [ind + TEAM_LOCK_RETURN_COMMENT, team_lock_line(values[side], ind)]
            done.append((side, int(bool(values[side]))))
        out.append(l)
    return out, done


# ------------------------------------------------------------------------------------------------ unlock points
# XML1 unlocks heroes at every mission start through data/missions/missions.xml charunlock and default.xbe's
# cumulative table (xml1build.unlocks, issue #55), not through a script or a conversation. The port puts that set
# (scripts.mission_start_unlocks) next to the mission's REQUIRED unlocks in the header of its begin body (research
# rewrite_scripts.mission_begin_lines: flag clears, setCurrentAct, objectives, REQUIRED unlocks, then the scriptstart
# body / load), in every copy of the body.
UNLOCK_COMMENT = '# ( "x1: XML1 unlocks %s at this mission start (missions.xml charunlock)" )'
_HEADER_STMT = re.compile(r'^\s*(setGameFlag|setCurrentAct|objective|unlockCharacter)\s*\(')
_UNLOCK_COMMENT_RE = re.compile(r'^\s*# \( "x1: XML1 unlocks \w+ at this mission ')


def mission_header_end(lines, i):
    """index just past the header of the begin body whose '# ( "XML1 beginMission(m)" )' marker is lines[i]: the
    run of setGameFlag / setCurrentAct / objective / unlockCharacter statements (and the comments the port puts
    there: the join reset, the team lock, the unlock-point comment) that research mission_begin_lines writes first."""
    j = i + 1
    while j < len(lines):
        s = lines[j].strip()
        if _HEADER_STMT.match(s) or _UNLOCK_COMMENT_RE.match(s) or s in (JOIN_RESET_COMMENT, TEAM_LOCK_COMMENT):
            j += 1
            continue
        break
    return j


def header_unlocks(lines, i):
    """[hero] unlocked by unlockCharacter("h", "" ) in the header of the begin body at marker line i."""
    out = []
    for l in lines[i + 1:mission_header_end(lines, i)]:
        m = _UNLOCK.match(l)
        if m:
            out.append(m.group('hero').lower())
    return out


def unlock_at_mission_starts(lines, unlocks):
    """-> (lines, [(mission, hero)]). unlocks: {mission: (hero, ...)}. After every '# ( "XML1 beginMission(m)" )'
    marker of a mission in `unlocks`, each hero its header does not unlock yet gets the unlock-point comment and
    unlockCharacter("h", "" ) at the end of the header (after the REQUIRED unlocks, before the movie / load).
    Idempotent."""
    out = list(lines)
    done = []
    edits = []
    for i, l in enumerate(out):
        m = BEGIN_MARKER.match(l.strip())
        if not m:
            continue
        mis = m.group('m').strip().lower()
        heroes = [h.lower() for h in unlocks.get(mis, ())]
        have = set(header_unlocks(out, i))
        new = []
        ind = l[:len(l) - len(l.lstrip())]
        for h in heroes:
            if h in have:
                continue
            new += [f'{ind}{UNLOCK_COMMENT % h}', f'{ind}unlockCharacter("{h}", "" )']
            done.append((mis, h))
        if new:
            edits.append((mission_header_end(out, i), new))
    for j, new in sorted(edits, key=lambda e: -e[0]):
        out[j:j] = new
    return out, done


# XML1 only SEATS a forced mission's REQUIRED heroes (party builder xbe 0x18d6d0 -> the slot setter, no unlock):
# Magma in the hubs and briefings before her dr_mag2 milestone, the two Professor X forms. Their unlock in the begin
# body's header (research mission_begin_lines: REQUIRED unlocks) therefore moves into the team-menu branch of the
# seat block (else: loadMapChooseTeam, xml2-fix [Game] ForcedTeams=0 or no DLL), where the player must be able to
# pick them; xml2-fix seatParty seats a hero without an unlock check.
MENU_UNLOCK_COMMENT = ('# ( "x1: the team menu needs %s unlocked; XML1 only seats this REQUIRED hero (no unlock '
                       'before its milestone)" )')


def menu_only_unlocks(lines, seat_only):
    """-> (lines, [(mission, hero)]). seat_only: {mission: (hero, ...)} - REQUIRED heroes of seated missions outside
    the mission's cumulative unlock set. For every begin-body marker of such a mission whose body carries the seat
    block (FT_SEAT_COMMENT ... if x1ft == 1 ... else ... endif) before the next begin marker, the header's
    unlockCharacter("h", "" ) lines of those heroes move to the start of the seat block's else branch. A body
    without a seat block keeps them (its start is a team menu). Idempotent."""
    out = list(lines)
    done = []
    i = 0
    while i < len(out):
        m = BEGIN_MARKER.match(out[i].strip())
        if not m:
            i += 1
            continue
        mis = m.group('m').strip().lower()
        heroes = [h.lower() for h in seat_only.get(mis, ())]
        if not heroes:
            i += 1
            continue
        end = mission_header_end(out, i)
        nxt = next((j for j in range(end, len(out)) if BEGIN_MARKER.match(out[j].strip())), len(out))
        seat = next((j for j in range(end, nxt) if out[j].strip() == FT_SEAT_COMMENT), None)
        if seat is None:
            i += 1
            continue
        ind = out[seat][:len(out[seat]) - len(out[seat].lstrip())]
        els = next((j for j in range(seat, nxt) if out[j] == f'{ind}else'), None)
        if els is None:
            i += 1
            continue
        move = [j for j in range(i + 1, end) if _UNLOCK.match(out[j]) and
                _UNLOCK.match(out[j]).group('hero').lower() in heroes]
        moved = [_UNLOCK.match(out[j]).group('hero').lower() for j in move]
        new = []
        for h in moved:
            new += [f'{ind}{IND}{MENU_UNLOCK_COMMENT % h}', f'{ind}{IND}unlockCharacter("{h}", "" )']
            done.append((mis, h))
        if not moved:
            i += 1
            continue
        out[els + 1:els + 1] = new
        for j in sorted(move, reverse=True):
            del out[j]
        i += 1
    return out, done


# Saves in progress (issue #55): XML1 keeps unlocks per save, so a save made by an earlier build of the port inside a
# mission lacks the heroes the mission start should have unlocked. XMen2.exe runs a zone's script when a saved game
# is loaded into that zone (verified in game, 2026-10-04), so the zone script of every zone whose XML1 world entity
# names a mission unlocks that mission's cumulative set again (unlockCharacter of an unlocked hero does nothing).
CATCHUP_COMMENT = '# ( "x1: this zone\'s mission unlocks (XML1 missions.xml charunlock) for saves made before them" )'
CATCHUP_END_COMMENT = '# ( "x1: end of the mission unlocks" )'


def catchup_unlocks(lines, heroes):
    """-> (lines, [hero]): CATCHUP_COMMENT + unlockCharacter("h", "" ) for each hero after the zone script's leading
    comments and its first statement when that is setCurrentAct (the act entry stays first). Idempotent."""
    if not heroes or any(l.strip() == CATCHUP_COMMENT for l in lines):
        return list(lines), []
    k = 0
    while k < len(lines) and (not lines[k].strip() or lines[k].lstrip().startswith('#')):
        k += 1
    if k < len(lines) and re.fullmatch(r'setCurrentAct\s*\(\s*\d+\s*\)', lines[k].strip()):
        k += 1
    new = [CATCHUP_COMMENT] + [f'unlockCharacter("{h.lower()}", "" )' for h in heroes] + [CATCHUP_END_COMMENT]
    return list(lines[:k]) + new + list(lines[k:]), [h.lower() for h in heroes]


def strip_generated_unlocks(lines):
    """lines without the unlocks this module generates (mission-start, team-menu and catch-up unlocks with their
    comments): what an analysis of XML1's own unlock sites (scripts._derive_post_branch_step) must look at."""
    out, block, skip = [], False, False
    for l in lines:
        s = l.strip()
        if s == CATCHUP_COMMENT:
            block = True
            continue
        if block:
            block = s != CATCHUP_END_COMMENT
            continue
        if skip and _UNLOCK.match(l):
            skip = False
            continue
        skip = bool(_UNLOCK_COMMENT_RE.match(s) or s.startswith('# ( "x1: the team menu needs '))
        if not skip:
            out.append(l)
    return out


def menu_only_problems(lines, seat_only):
    """-> [problem] for menu_only_unlocks' output: a begin body of a mission in `seat_only` that carries the seat
    block still unlocks one of those heroes in its header (XML1 never unlocked them there)."""
    probs = []
    for i, l in enumerate(lines):
        m = BEGIN_MARKER.match(l.strip())
        if not m:
            continue
        mis = m.group('m').strip().lower()
        heroes = {h.lower() for h in seat_only.get(mis, ())}
        if not heroes:
            continue
        end = mission_header_end(lines, i)
        nxt = next((j for j in range(end, len(lines)) if BEGIN_MARKER.match(lines[j].strip())), len(lines))
        if not any(lines[j].strip() == FT_SEAT_COMMENT for j in range(end, nxt)):
            continue
        for h in sorted(heroes & set(header_unlocks(lines, i))):
            probs.append(f'line {i + 1}: beginMission({mis}) unlocks {h}, whom XML1 only seats (issue #55)')
    return probs


def unlock_problems(lines, unlocks):
    """-> ([problem], copies) for unlock_at_mission_starts' output: every begin-body marker of a mission in
    `unlocks` has exactly one unlockCharacter("h", "" ) per hero in its header (copies = markers checked)."""
    probs, copies = [], 0
    for i, l in enumerate(lines):
        m = BEGIN_MARKER.match(l.strip())
        if not m:
            continue
        mis = m.group('m').strip().lower()
        if mis not in unlocks:
            continue
        copies += 1
        got = collections.Counter(header_unlocks(lines, i))
        for h in unlocks[mis]:
            if got[h.lower()] != 1:
                probs.append(f'line {i + 1}: beginMission({mis}) header unlocks {h} {got[h.lower()]} times (want 1)')
    return probs, copies


# ------------------------------------------------------------------------------------------------ interpreter
def run_pack_ops(lines, flags, env=None, funcs=None, trace=None):
    """Execute the pack-code subset of a script: returns env. flags: {(g, bit): 0|1} (modified in place).
    funcs: {name: fn(args list) -> value} for other assigned calls (default 0); trace: a list that gets
    (name, args text) of every other call statement that runs (selftests of the forced-team blocks)."""
    env = dict(env or {})
    funcs = funcs or {}

    def val(tok):
        tok = tok.strip()
        if re.fullmatch(r'-?\d+(\.\d+)?', tok):
            return int(float(tok))
        return env.get(tok, 0)

    def call(fn, args):
        a = [x.strip() for x in args.split(',')] if args.strip() else []
        if fn == 'getGameFlag':
            return flags.get((a[0].strip('"\''), int(a[1])), 0)
        if fn == 'iadd':
            return val(a[0]) + val(a[1])
        if fn == 'isub':
            return val(a[0]) - val(a[1])
        if fn == 'imul':
            return val(a[0]) * val(a[1])
        if fn == 'idiv':
            x, y = val(a[0]), val(a[1])
            return int(x / y) if y else 0            # C truncation towards zero
        if fn in funcs:
            return funcs[fn](a)
        return 0

    stack = []                                        # [(active, taken)]
    for raw in lines:
        s = _canon(raw)
        if not s or s.startswith('#'):
            continue
        active = all(a for a, _ in stack)
        m = re.fullmatch(r'(if|elif|elseif) (\w+) (==|!=|<=|>=|<|>) (-?[\w.]+)', s)
        if m:
            kw = m.group(1)
            if kw == 'if':
                cond = active and _cmp(val(m.group(2)), m.group(3), val(m.group(4)))
                stack.append([cond, cond])
            else:
                top = stack[-1]
                outer = all(a for a, _ in stack[:-1])
                cond = outer and not top[1] and _cmp(val(m.group(2)), m.group(3), val(m.group(4)))
                top[0] = cond
                top[1] = top[1] or cond
            continue
        if s == 'else':
            top = stack[-1]
            outer = all(a for a, _ in stack[:-1])
            top[0] = outer and not top[1]
            top[1] = True
            continue
        if s == 'endif':
            stack.pop()
            continue
        if not active:
            continue
        m = re.fullmatch(r'(\w+) = (\w+)\((.*)\)', s)
        if m:
            env[m.group(1)] = call(m.group(2), m.group(3))
            continue
        m = re.fullmatch(r'(\w+) = (-?[\w.]+)', s)
        if m:
            env[m.group(1)] = val(m.group(2))
            continue
        m = re.fullmatch(r'setGameFlag\((.*)\)', s)
        if m:
            a = [x.strip() for x in m.group(1).split(',')]
            flags[(a[0].strip('"\''), int(a[1]))] = 1 if val(a[2]) else 0
            continue
        m = re.fullmatch(r'(\w+) ?\((.*)\)', s)
        if m and trace is not None:
            trace.append((m.group(1), m.group(2).strip()))
    return env


def _cmp(a, op, b):
    return {'==': a == b, '!=': a != b, '<=': a <= b, '>=': a >= b, '<': a < b, '>': a > b}[op]


def gen_get(target, g, b, n, signed):
    """rewrite_scripts.gen_get's exact output (for tests)."""
    lines = [f'{target} = {_call("getGameFlag", chr(34) + g + chr(34), b)}']
    for i in range(1, n):
        lines += [f'x1_b = {_call("getGameFlag", chr(34) + g + chr(34), b + i)}', f'x1_b = {_call("imul", "x1_b", 1 << i)}',
                  f'{target} = {_call("iadd", target, "x1_b")}']
    if signed:
        lines += [SIGN_COMMENT, f'if {target} >= {1 << (n - 1)}', f'     {target} = {_call("isub", target, 1 << n)}',
                  'endif']
    return lines


def gen_set(expr, g, b, n, signed):
    """rewrite_scripts.gen_set's exact output for a variable value (for tests)."""
    lines = [f'x1_t = {_call("iadd", expr, 0)}']
    if signed:
        lines += [SIGN_COMMENT, 'if x1_t < 0', f'     x1_t = {_call("iadd", "x1_t", 1 << n)}', 'endif']
    for i in range(n):
        lines += [f'x1_q = {_call("idiv", "x1_t", 2)}', f'x1_r = {_call("imul", "x1_q", 2)}',
                  f'x1_r = {_call("isub", "x1_t", "x1_r")}', _call('setGameFlag', chr(34) + g + chr(34), b + i, 'x1_r')]
        if i + 1 < n:
            lines.append(f'x1_t = {_call("iadd", "x1_q", 0)}')
    return lines


def gen_set_literal(x, g, b, n):
    x &= (1 << n) - 1
    return [_call('setGameFlag', chr(34) + g + chr(34), b + i, (x >> i) & 1) for i in range(n)]


def selftest():
    """Narrowed read/write/literal blocks round-trip every value of the narrowed range (unsigned and signed,
    indented, inside if-blocks). Returns a list of failures."""
    fails = []
    for signed, n, k in ((False, 8, 3), (True, 8, 5), (False, 8, 1), (True, 8, 2)):
        sp = NarrowSpec('t', 'x1v09', 7, n, k, signed)
        lo, hi = (-(1 << (k - 1)), 1 << (k - 1)) if signed else (0, 1 << k)
        body = ['# test', 'cc = 0'] + gen_get('cc', 'x1v09', 7, n, signed) + \
               ['cc = iadd(cc, 1 )'] + gen_set('cc', 'x1v09', 7, n, signed) + ['x = 1', 'if x == 1'] + \
               ['     ' + l for l in gen_get('dd', 'x1v09', 7, n, signed)] + ['endif']
        new, ch, probs = narrow_packed(body, [sp])
        if probs:
            fails.append(f'{sp}: {probs}')
            continue
        want = {'read:t': 2, 'write:t': 1}
        if dict(ch) != want:
            fails.append(f'{sp}: changes {dict(ch)} != {want}')
        refs = [bb for l in new for mm in _FLAG_RE.finditer(l) for bb in [int(mm.group(4))] if bb >= 7 + k]
        if refs:
            fails.append(f'{sp}: high bits still referenced {refs}')
        for v in range(lo, hi - 1):                    # v + 1 must still fit
            flags = {}
            for l in gen_set_literal(v, 'x1v09', 7, n):          # stored by an old (full-width) literal write
                run_pack_ops([l], flags)
            env = run_pack_ops(new, flags)
            if env.get('cc') != v + 1 or env.get('dd') != v + 1:
                fails.append(f'{sp}: value {v}: read back cc={env.get("cc")} dd={env.get("dd")} (want {v + 1})')
                break
        # literal runs are narrowed; an out-of-range literal is refused
        lit = gen_set_literal(hi - 1, 'x1v09', 7, n) + gen_set_literal(0, 'x1v08', 1, 4)
        new2, ch2, probs2 = narrow_packed(lit, [sp])
        if probs2 or ch2.get('literal:t') != 1 or len(new2) != k + 4:
            fails.append(f'{sp}: literal run narrowing {probs2} {dict(ch2)} {len(new2)}')
        bad = gen_set_literal(hi, 'x1v09', 7, n)
        _, _, probs3 = narrow_packed(bad, [sp])
        if not probs3:
            fails.append(f'{sp}: out-of-range literal {hi} was not refused')
    # a stray reference to a narrowed high bit makes the transform refuse
    sp = NarrowSpec('t', 'x1v09', 7, 8, 3, False)
    _, _, probs = narrow_packed(['v = getGameFlag("x1v09", 12 )'], [sp])
    if not probs:
        fails.append('stray high-bit read was not refused')
    # zone literals / blackbird
    t, ch = normalise_zone_literals('loadMapKeepTeam("mocap/mocap2/Briefing_1_2_41" )\r\n'
                                    'blackbirdMenu("FALSE", "loadMapKeepTeam(\'Hive/H_Ext/hive1_1_1\')", "TRUE" )\r\n'
                                    'cinematicStart("subtitles/x", "mocap/mocap4/Briefing_1_7_1_cancel" )\r\n'
                                    'loadZone("Sewers\\GRSO/sewers3_1_1", "Start1" )')
    want = ('loadMapKeepTeam("mocap/mocap2/briefing_1_2_41" )\r\n'
            'blackbirdMenu("FALSE", "loadMapKeepTeam(\'hive/h_ext/hive1_1_1\')", "TRUE" )\r\n'
            'cinematicStart("subtitles/x", "mocap/mocap4/briefing_1_7_1_cancel" )\r\n'
            'loadZone("sewers/grso/sewers3_1_1", "Start1" )')
    if t != want:
        fails.append(f'normalise_zone_literals: {t!r}')
    bb, zs = blackbird_to_choose_team(['     blackbirdMenu("FALSE", "loadMapKeepTeam(\'haarp/ext/haarp_ext01\')", "TRUE" )',
                                       'blackbirdMenu("false", "e3/mansion1", "map" )'])
    if bb != ['     loadMapChooseTeam("haarp/ext/haarp_ext01" )', 'blackbirdMenu("false", "e3/mansion1", "map" )'] \
            or zs != ['haarp/ext/haarp_ext01']:
        fails.append(f'blackbird_to_choose_team: {bb} {zs}')
    # mission anims: enum (any case, inside inline data quoting) and combat-node literals; n > 20 untouched
    t, ch = rename_mission_anims('playanim("EA_MISSION14", "_OWNER_", "", "" )\r\n'
                                 "x = playanim ('ea_mission1', '_OWNER_', 'LOOP', '')\r\n"
                                 'playanim("EA_mission12", "a" )\r\n'
                                 'loopCombatNode("cyclops", "mission1", "LOOP" )\r\n'
                                 'setCombatNode("storm", "mission20" )\r\n'
                                 'playanim("EA_MISSION21" ) x = "chose_mission2" mission_mocap1 EA_MISSIONARY')
    want = ('playanim("EA_ZONE14", "_OWNER_", "", "" )\r\n'
            "x = playanim ('ea_zone1', '_OWNER_', 'LOOP', '')\r\n"
            'playanim("EA_zone12", "a" )\r\n'
            'loopCombatNode("cyclops", "zone1", "LOOP" )\r\n'
            'setCombatNode("storm", "zone20" )\r\n'
            'playanim("EA_MISSION21" ) x = "chose_mission2" mission_mocap1 EA_MISSIONARY')
    if t != want or len(ch) != 5:
        fails.append(f'rename_mission_anims: {t!r} {ch}')
    if rename_mission_anims(want)[1]:
        fails.append('rename_mission_anims is not idempotent')
    # forced heroes: only the matching body span, nested marker of another mission left to its own entry
    body = ['# ( "XML1 beginMission(mansion1)" )', 'setCurrentAct(1 )', 'unlockCharacter("magma", "" )',
            'loadMapKeepTeam("mansion/man1a/mansion1a_1" )']
    src = ['# Generated by BehavEd', 'cameraReset( )', '# ( "XML1 beginMission(mansion1)" )', 'setCurrentAct(1 )',
           'unlockCharacter("magma", "" )', '     loadMapKeepTeam("mansion/man1a/mansion1a_1" )',
           'loadMapKeepTeam("other/zone" )', '# ( "XML1 beginMission(haarp)" )', 'loadMapKeepTeam("haarp/x" )']
    got, ch = choose_team_in_bodies(src, {'mansion1': body})
    want = src[:5] + ['     loadMapChooseTeam("mansion/man1a/mansion1a_1" )'] + src[6:]
    if got != want or ch != [('mansion1', 'loadMapChooseTeam("mansion/man1a/mansion1a_1" )')]:
        fails.append(f'choose_team_in_bodies: {got} {ch}')
    got, ch = choose_team_in_bodies(src, {'mansion1': body[:2] + ['different']})
    if got != src or ch:
        fails.append('choose_team_in_bodies changed a span that does not match the body')
    # act injection
    got = inject_act(['# Generated by BehavEd', '# ( "x" )', '', 'foo( )'], 7)
    if got != ['# Generated by BehavEd', '# ( "x" )', '', ACT_COMMENT, 'setCurrentAct(7 )', 'foo( )'] \
            or first_statement_act(got) != 7 or first_statement_act(['# a', 'foo( )']) is not None:
        fails.append(f'inject_act: {got}')
    # bounded LOOP_WAKE (npc-loop fix): last statement of a script file, XML1's own spacing kept; a comment after
    # it does not count; an owner that is not _OWNER_, another mode, or a statement after it is left alone
    src = ['# Generated by BehavEd', 'addBolton("_OWNER_", "models/bolton/baseball_bat", "Bip01 R Hand", "Grab1", 1 )',
           'playanim (  "EA_ZONE3", "_OWNER_", "LOOP_WAKE", "" )', '# ( "trailing comment" )', '']
    got, ch, sk = bound_unwakeable_loops(src, 15.0)
    want = src[:2] + ['playanim (  "EA_ZONE3", "_OWNER_", "LOOP", "" )', UNWAKEABLE_COMMENT, 'waittimed ( 15.000 )',
                      'playanim (  "EA_ZONE3", "_OWNER_", "STOP", "" )'] + src[3:]
    if got != want or ch != [('EA_ZONE3', 2)] or sk:
        fails.append(f'bound_unwakeable_loops: {got} {ch} {sk}')
    got2, ch2, sk2 = bound_unwakeable_loops(want, 15.0)
    if got2 != want or ch2 or sk2:
        fails.append('bound_unwakeable_loops is not idempotent')
    keep = ['playanim (  "EA_ZONE1", "scarymonster", "LOOP_WAKE", "" )', "playanim ('EA_ZONE2', '_OWNER_', 'LOOP', '')",
            'loopCombatNode("_ACTIVATOR_", "forcefield", "LOOP_WAKE" )']
    if bound_unwakeable_loops(keep, 15.0) != (keep, [], []):
        fails.append('bound_unwakeable_loops touched a statement it must keep')
    got, ch, sk = bound_unwakeable_loops(['playanim("EA_ZONE4", "_OWNER_", "loop_wake", "" )', 'foo( )'], 15.0)
    if ch or sk != [('EA_ZONE4', 0)] or got[0] != 'playanim("EA_ZONE4", "_OWNER_", "loop_wake", "" )':
        fails.append(f'bound_unwakeable_loops rewrote a non-final statement: {got} {ch} {sk}')
    got, ch, sk = bound_unwakeable_loops(["playanim ('EA_ZONE3', '_OWNER_', 'LOOP_WAKE', '') "], 15.0, inline=True)
    if got != ["playanim ('EA_ZONE3', '_OWNER_', 'LOOP', '') ", 'waittimed(15)', "playanim ('EA_ZONE3', '_OWNER_', 'STOP', '')"] \
            or ch != [('EA_ZONE3', 0)]:
        fails.append(f'bound_unwakeable_loops inline: {got}')
    # T7 join_hero: the research's addHero emulation (unlock x2 + extractionPointLite) -> unlock, remove the NPC,
    # set the join bit, extractionPointChange; the waits and the popup move before the block, the popup followed by
    # a waittimed (it runs out only once the popup is closed: the team menu / reload comes after it); idempotent
    src = ['# Generated by BehavEd', 'sound (  "PLAY_SOUND", "voice/cyclops/1_1_0045_1", "", "" )', 'waittimed ( 1.000 )',
           'unlockCharacter("cyclops", "" )', 'unlockCharacter("cyclops", "" )',
           'extractionPointLite("_ACTIVE_HERO_", "true", "false", "false" )', 'waittimed ( 1.000 )',
           'createPopupDialogXml("dialogs/tut15" )', '']
    got, heroes, pops = join_hero(src, 1)
    want = src[:3] + ['waittimed ( 1.000 )', JOIN_POPUP_COMMENT, 'createPopupDialogXml("dialogs/tut15" )',
                      'waittimed ( 0.500 )', 'unlockCharacter("cyclops", "" )',
                      JOIN_COMMENT % 'cyclops', 'remove ( "cyclops_x1double", "cyclops_x1double" )',
                      'setGameFlag("x1join", 1, 1 )', 'extractionPointChange("_ACTIVE_HERO_", 0 )', '']
    if got != want or heroes != ['cyclops'] or pops != ['dialogs/tut15']:
        fails.append(f'join_hero: {got} {heroes} {pops}')
    if join_hero(want, 1) != (want, [], []):
        fails.append('join_hero is not idempotent')
    got, _, _ = join_hero(src[:-2] + ['createPopupDialogXml("dialogs/tut15" )', 'waittimed ( 2.000 )', ''], 1)
    if got.count('waittimed ( 0.500 )') or got.count('waittimed ( 2.000 )') != 1:
        fails.append(f'join_hero added a second wait after a popup that has one: {got}')
    if join_hero(['extractionPointLite("_ACTIVE_HERO_", "true", "false", "false" )'], 1)[1]:
        fails.append('join_hero rewrote an extractionPointLite without a preceding unlock')
    # zone guard after the leading setCurrentAct; idempotent
    z = ['# Created by Clem', '# ( "act" )', 'setCurrentAct(1 )', '    setGameFlag("x1v06", 20, 0 )']
    got, ins = join_hero_zone_guard(z, 1, late=())
    want = z[:3] + [JOIN_GUARD_COMMENT, 'x1j = getGameFlag("x1join", 1 )', 'if x1j == 1',
                    '     remove ( "trigger_touch03", "trigger_touch03" )', '     remove ( "sp_cyclops01", "sp_cyclops01" )',
                    '     remove ( "cyclops_x1double", "cyclops_x1double" )', 'endif'] + z[3:]
    if got != want or not ins:
        fails.append(f'join_hero_zone_guard: {got}')
    if join_hero_zone_guard(want, 1, late=()) != (want, False):
        fails.append('join_hero_zone_guard is not idempotent')
    got, ins = join_hero_zone_guard(['# x', 'foo( )'], 2)
    if got[:2] != ['# x', JOIN_GUARD_COMMENT] or got[got.index('foo( )') + 1] != JOIN_LATE_COMMENT:
        fails.append(f'join_hero_zone_guard without setCurrentAct: {got}')
    # the double again at the end of the zone script (the spawner's instant spawn comes after the guard's removes)
    zf = z + ['debug("x" )', '']
    got, ins = join_hero_zone_guard(zf, 1)
    late = got[got.index(JOIN_LATE_COMMENT):]
    if not ins or late[1] != 'if x1j == 1' or late[-2:] != ['endif', ''] or got[3] != JOIN_GUARD_COMMENT or \
            late[2:-2] != [x for w in JOIN_LATE_REMOVE_WAITS
                           for x in (f'     waittimed ( {w} )', '     remove ( "cyclops_x1double", "cyclops_x1double" )')]:
        fails.append(f'join_hero_zone_guard late removes: {got}')
    if join_hero_zone_guard(got, 1) != (got, False):
        fails.append('join_hero_zone_guard (late removes) is not idempotent')
    n = len(JOIN_LATE_REMOVE_WAITS)
    for bits, want_calls in (({('x1join', 1): 1},
                              ['setCurrentAct'] + ['remove'] * 3 + ['debug'] + ['waittimed', 'remove'] * n),
                             ({}, ['setCurrentAct', 'debug'])):
        trace = []
        run_pack_ops(got, dict(bits), trace=trace)
        if [c for c, _ in trace] != want_calls:
            fails.append(f'join zone guard runtime {bits}: {trace}')
    # mission-start reset after the marker; other missions untouched; idempotent
    b = ['# Generated by rewrite_scripts.py', '# ( "XML1 beginMission(alison)" )', 'setGameFlag("x1v06", 19, 0 )',
         '# ( "XML1 beginMission(haarp)" )', 'foo( )']
    got, done = join_hero_mission_reset(b, {'alison': 1, 'dr_mag2': 2})
    want = b[:2] + [JOIN_RESET_COMMENT, 'setGameFlag("x1join", 1, 0 )'] + b[2:]
    if got != want or done != [('alison', 1)]:
        fails.append(f'join_hero_mission_reset: {got} {done}')
    if join_hero_mission_reset(want, {'alison': 1})[0] != want:
        fails.append('join_hero_mission_reset is not idempotent')
    # unlock points: after the REQUIRED unlocks of every copy of the body (nested / indented too); idempotent
    b = ['# Generated by rewrite_scripts.py', '# ( "XML1 beginMission(mansion2)" )', 'setGameFlag("mansion2", 1, 0 )',
         'setCurrentAct(1 )', 'objective("warroom", "EOBJCMD_INCOMPLETE" )', 'unlockCharacter("magma", "" )',
         'startMovie("r103", "afterMovie" )', 'if x == 1', '     # ( "XML1 beginMission(mansion2)" )',
         '     setCurrentAct(1 )', '     loadMapKeepTeam("mansion/man2/mansion_back2" )', 'endif',
         '# ( "XML1 beginMission(haarp)" )', 'setCurrentAct(1 )']
    ul = {'mansion2': ('jubilee',)}
    got, done = unlock_at_mission_starts(b, ul)
    want = b[:6] + [UNLOCK_COMMENT % 'jubilee', 'unlockCharacter("jubilee", "" )'] + b[6:10] + \
        ['     ' + UNLOCK_COMMENT % 'jubilee', '     unlockCharacter("jubilee", "" )'] + b[10:]
    if got != want or done != [('mansion2', 'jubilee'), ('mansion2', 'jubilee')]:
        fails.append(f'unlock_at_mission_starts: {got} {done}')
    if unlock_at_mission_starts(got, ul) != (got, []):
        fails.append('unlock_at_mission_starts is not idempotent')
    if unlock_problems(got, ul) != ([], 2) or unlock_problems(b, ul)[1] != 2 or len(unlock_problems(b, ul)[0]) != 2:
        fails.append(f'unlock_problems: {unlock_problems(got, ul)} / {unlock_problems(b, ul)}')
    dup = got[:7] + ['unlockCharacter("jubilee", "" )'] + got[7:]
    if not unlock_problems(dup, ul)[0]:
        fails.append('unlock_problems missed a duplicate unlock')
    # SPEC 18 same-name NPCs: entity arguments follow the double; hero-name arguments of other calls stay
    src = ['playanim (  "EA_ZONE1", "wolverine", "NONE", "" )', "setEnable('Cyclops', 'FALSE' )",
           '# ( "wolverine" )', 'unlockCharacter("wolverine", "" )', 'seatParty("magma", "wolverine", "", "" )',
           'objective("cyclops", "EOBJCMD_SHOW" )', 'faceEntity("storm", "cyclops" )', 'playanim (  "EA_ZONE4", "beast", "NONE", "" )']
    got, n = rename_npc_refs(src, {'wolverine', 'cyclops'})
    want = ['playanim (  "EA_ZONE1", "wolverine_x1double", "NONE", "" )', "setEnable('cyclops_x1double', 'FALSE' )"] + \
        src[2:6] + ['faceEntity("storm", "cyclops_x1double" )', src[7]]
    if got != want or n != 3 or rename_npc_refs(got, {'wolverine', 'cyclops'}) != (got, 0):
        fails.append(f'rename_npc_refs: {got} {n}')
    if [entity_name_refs(l, {'wolverine', 'cyclops', 'storm'}) for l in src[3:7]] != [[], [], [], [('faceEntity', 'storm'), ('faceEntity', 'cyclops')]]:
        fails.append('entity_name_refs')
    # SPEC 18.1 speaker tokens: a double's token, or the NPC's own name (NPC_SPEAKER_CONVERSATIONS); idempotent
    for heroes, text, want in (({'colossus'}, '%COLOSSUS%Hi %Colossus%', '%COLOSSUS_X1DOUBLE%Hi %COLOSSUS_X1DOUBLE%'),
                               ({'cyclops': 'cyclops_scripted'}, '%CYCLOPS%Hey, Wolverine.', '%CYCLOPS_SCRIPTED%Hey, Wolverine.'),
                               ({'cyclops': 'cyclops_scripted'}, '%WOLVERINE%C\'mon!', '%WOLVERINE%C\'mon!')):
        got = rename_speaker_tokens(text, heroes)
        if got[0] != want or rename_speaker_tokens(got[0], heroes) != (got[0], 0):
            fails.append(f'rename_speaker_tokens({heroes}, {text!r}): {got}')
    if speaker_stats_entries().get('cyclops_scripted') != 'cyclops' or speaker_stats_entries().get('gambit_x1double') != 'gambit':
        fails.append(f'speaker_stats_entries: {speaker_stats_entries()}')
    if npc_speaker_renames('Nyc/Alison/1_1_09') != {'cyclops': 'cyclops_scripted'} or npc_speaker_renames('nyc/alison/1_1_5_1d'):
        fails.append('npc_speaker_renames')
    # the NPC Alison (XML1's %ALISON%, already %MAGMA% after scripts.SPEAKER_TOKEN_ALIASES) and the NPC Emma
    for conv, text, want in (('nyc/alison/1_1_5_1b', '%MAGMA%Line text.', '%ALISON%Line text.'),
                             ('mansion/dr_mag2/2_2_1_3b', '%MAGMA%Line', '%ALISON_SCRIPTED%Line'),
                             ('mansion/man4/2_5_10', '%FROST%Hello, Alison.', '%EMMA%Hello, Alison.'),
                             ('mansion/man4/2_5_10b', '%MAGMA%Yes, my name is Alison Crestmere.', '%MAGMA%Yes, my name is Alison Crestmere.')):
        got = rename_speaker_tokens(text, npc_speaker_renames(conv))[0]
        if got != want:
            fails.append(f'npc_speaker_renames({conv}) on {text!r}: {got!r}')
    if npc_speaker_renames('mansion/dr_mag2/2_2_1_3a') or npc_speaker_renames('mansion/dr_mag2/2_2_1_3_new'):
        fails.append('npc_speaker_renames: the party Magma lines of mag_nyc4 must keep %MAGMA%')
    if speaker_stats_entries().get('alison') != 'magma' or speaker_stats_entries().get('emma') != 'frost' \
            or not set(SPEAKER_DISPLAY_NAMES) <= set(speaker_stats_entries()):
        fails.append(f'speaker_stats_entries / SPEAKER_DISPLAY_NAMES: {speaker_stats_entries()}')
    # SPEC 21 C.4.2: imageViewer literals follow the review namespace; everything else untouched; idempotent
    ns = {'textures/comic/beast_cov.png': 'textures/comic/x1/beast_cov',
          'textures/comic/0901.png': 'textures/comic/x1/col_cov',
          'textures/concept/concept07': 'textures/concept/x1/concept07'}

    def mapper(p):
        return ns.get(p.lower(), 'textures/concept/x1/' + p.lower().rsplit('/', 1)[-1]
                      if p.lower().startswith('textures/concept/') and '/x1/' not in p.lower() else p.lower())
    src = "setGameFlag('a',1,1 )\r\nimageViewer('textures/comic/beast_cov.png')\r\nimageViewer( \"textures/comic/0901.png\" )\r\n" \
          "remove('x')|imageViewer('textures/concept/concept07')|startMovie('i101','s')"
    got, ch = rewrite_image_viewer(src, mapper)
    want = "setGameFlag('a',1,1 )\r\nimageViewer('textures/comic/x1/beast_cov')\r\nimageViewer( \"textures/comic/x1/col_cov\" )\r\n" \
           "remove('x')|imageViewer('textures/concept/x1/concept07')|startMovie('i101','s')"
    if got != want or len(ch) != 3 or rewrite_image_viewer(got, mapper) != (got, []):
        fails.append(f'rewrite_image_viewer: {got!r} {ch}')
    inline = "waittimed(0.5)\\n\\rimageViewer('textures/comic/beast_cov.png')"      # the zone pickups' form
    if rewrite_image_viewer(inline, mapper)[0] != "waittimed(0.5)\\n\\rimageViewer('textures/comic/x1/beast_cov')":
        fails.append(f'rewrite_image_viewer after the literal \\n\\r separator: {rewrite_image_viewer(inline, mapper)}')
    fails += _forced_teams_selftest()
    return fails


# no \b: inline data code separates statements with the literal '\n\r', so a call follows the letter 'r'
_IMAGE_VIEWER = re.compile(r'''(imageViewer\s*\(\s*)(['"])([^'"\r\n]*)(\2)''', re.I)


def rewrite_image_viewer(text, mapper):
    """SPEC 21 C.4.2: the path literal of every imageViewer(...) call -> mapper(path) (common.map_review_texture:
    textures/comic/X.png -> textures/comic/x1/X, textures/concept/Y -> textures/concept/x1/Y). XMen2.exe's
    imageViewer (0x49e440) no longer opens a viewer: it unlocks the Review entry whose value equals the path up to
    its first '.' (0x4ae530), in the 'concept' or 'comic' category by substring. Quotes and spacing are kept.
    Returns (text, [(old, new)])."""
    changes = []

    def sub(m):
        old = m.group(3)
        new = mapper(old)
        if not new or new == old:
            return m.group(0)
        changes.append((old, new))
        return f'{m.group(1)}{m.group(2)}{new}{m.group(4)}'
    return _IMAGE_VIEWER.sub(sub, text), changes


def _drop_xml2fix(lines):
    """the script as XMen2.exe compiles it without the xml2-fix functions: their statements are dropped."""
    return [l for l in lines if not any(re.search(r'\b%s\s*\(' % f, l) for f in XML2FIX_API)]


def _run_forced(lines, dll=True, features=(FT_FEATURE,), add_hero_ok=1, join_hero_ok=1, flags=None):
    """(trace of the bare calls that run, env) of a forced-team block: dll=False drops the xml2-fix statements."""
    trace = []
    funcs = {'xml2fixFeature': lambda a: 1 if a and a[0].strip('"\'') in features else 0,
             'addHero': lambda a: add_hero_ok, 'joinHero': lambda a: join_hero_ok}
    env = run_pack_ops(lines if dll else _drop_xml2fix(lines), {} if flags is None else flags, funcs=funcs,
                       trace=trace)
    return [c for c, _ in trace], env


def _forced_teams_selftest():
    """forced_party_in_bodies / side push / side end / join_hero(add_hero) / xml2fix_guard_problems: shapes,
    idempotence, the three runtime cases (DLL with the feature on, DLL with it off, no DLL) and the guard rule."""
    fails = []
    body = ['# ( "XML1 beginMission(mansion1)" )', 'setCurrentAct(1 )', 'unlockCharacter("magma", "" )',
            'startMovie("r103", "afterMovie" )', 'waitsignal ( "afterMovie" )',
            'loadMapChooseTeam("mansion/man1a/mansion1a_1" )']
    free = ['# ( "XML1 beginMission(haarp)" )', 'setCurrentAct(1 )',
            'blackbirdMenu("FALSE", "loadMapKeepTeam(\'haarp/ext/haarp_ext01\')", "TRUE" )', 'debug("x1: removed statement" )']
    plan = {'mansion1': {'status': 'seat', 'seat': ['magma'], 'costume': 'civilian', 'heroes': 'magma'},
            'haarp': {'status': 'free', 'seat': [], 'costume': 'default', 'heroes': ''}}
    bodies = {'mansion1': [l.strip() for l in body], 'haarp': [l.strip() for l in free]}
    src = ['# Generated by rewrite_scripts.py'] + body + ['# a briefing that inlines the start', 'if x == 1'] + \
          ['     ' + l for l in body] + ['endif'] + free
    got, ch = forced_party_in_bodies(src, bodies, plan)
    seat = seat_block('', ['magma'], 'civilian', 'magma', 'mansion/man1a/mansion1a_1')
    want = ['# Generated by rewrite_scripts.py'] + body[:-1] + seat + ['# a briefing that inlines the start', 'if x == 1'] + \
           ['     ' + l for l in body[:-1]] + ['     ' + l for l in seat] + ['endif'] + free[:2] + \
           skinset_block('', 'default', '') + free[2:]
    if got != want or [k for _, k, _ in ch] != ['skinset', 'seat', 'seat']:
        fails.append(f'forced_party_in_bodies: {got} {ch}')
    if forced_party_in_bodies(got, bodies, plan)[0] != got:
        fails.append('forced_party_in_bodies is not idempotent')
    if seat[3:] != ['if x1ft == 1', '     seatParty("magma", "", "", "" )', '     setSkinset("civilian", "magma" )',
                    '     loadMapKeepTeam("mansion/man1a/mansion1a_1" )', 'else',
                    '     loadMapChooseTeam("mansion/man1a/mansion1a_1" )', 'endif'] or \
            seat[1:3] != ['x1ft = iadd(0, 0 )', 'x1ft = xml2fixFeature("forcedteams" )']:
        fails.append(f'seat_block shape: {seat}')
    part = [l for l in body if l.strip() != 'setCurrentAct(1 )']
    if forced_party_in_bodies(['# x'] + part, bodies, plan)[0] != ['# x'] + part:
        fails.append('forced_party_in_bodies changed a span that does not match the body')
    # runtime: seat with the DLL + ForcedTeams=1; team menu with ForcedTeams=0 and without the DLL
    calls, _ = _run_forced(seat)
    if calls != ['seatParty', 'setSkinset', 'loadMapKeepTeam']:
        fails.append(f'seat block with ForcedTeams=1 runs {calls}')
    for dll, feats in ((True, ()), (False, (FT_FEATURE,))):
        calls, env = _run_forced(seat, dll=dll, features=feats)
        if calls != ['loadMapChooseTeam'] or env.get(FT_VAR) != 0:
            fails.append(f'seat block (dll={dll}, features={feats}) runs {calls}, {FT_VAR}={env.get(FT_VAR)}')
    skin = skinset_block('', 'default', '')
    if _run_forced(skin)[0] != ['debug', 'setSkinset'] or _run_forced(skin, dll=False)[0] != [] or \
            _run_forced(skin, features=())[0] != []:
        fails.append(f'skinset block runtime: {skin}')
    if _drop_xml2fix(skin)[2:4] != ['if x1ft == 1', '     ' + FT_KEEP]:
        fails.append('skinset block branch is empty without the DLL')
    # side missions: push after the script-site marker, before an inline side script's own marker; pop at the end
    site = ['# ( "XML1 beginSideMission(jug_fb) - return handled by endSideMission rewrite" )',
            '# ( "XML1 beginMission(jug_fb)" )', 'loadMapChooseTeam("mansion/jugrnt/jugrnt01" )']
    got, done = side_push_at_markers(site, {'jug_fb'})
    if got != site[:1] + push_block() + site[1:] or done != ['jug_fb']:
        fails.append(f'side_push_at_markers: {got} {done}')
    if side_push_at_markers(got, {'jug_fb'})[0] != got or side_push_at_markers(site, {'sent_fb'})[0] != site:
        fails.append('side_push_at_markers is not idempotent / touched another side mission')
    inl = ['# Generated by rewrite_scripts.py', '# ( "XML1 beginMission(dr_mag1)" )', 'loadZone("x", "" )']
    got, ins = side_push_before_marker(inl, 'dr_mag1')
    if not ins or got != inl[:1] + push_block() + inl[1:] or side_push_before_marker(got, 'dr_mag1') != (got, False):
        fails.append(f'side_push_before_marker: {got}')
    if _run_forced(push_block())[0] != ['debug', 'pushParty'] or _run_forced(push_block(), dll=False)[0]:
        fails.append('push block runtime')
    end = ['if iDone == 1', '     waittimed ( 1.000 )', '     # ( "XML1 endSideMission from side mission sent_fb" )',
           '     setCurrentAct(1 )', '     loadZone("mansion/man2/mansion2_1", "" )', 'endif',
           '# ( "XML1 endSideMission from side mission astral_sk" )', 'setCurrentAct(9 )',
           'loadZone("astral/savepx/astral2_3", "" )']
    got, done, probs = side_end_at_markers(end, {'sent_fb': ('civilian', 'magma'), 'astral_sk': None})
    want = end[:4] + pop_block('     ', 'civilian', 'magma', 'mansion/man2/mansion2_1') + end[5:8] + \
        [FT_T9_COMMENT, 'loadMapChooseTeam("astral/savepx/astral2_3" )']
    if got != want or probs or [k for _, _, k in done] != ['pop', 'menu']:
        fails.append(f'side_end_at_markers: {got} {done} {probs}')
    if side_end_at_markers(got, {'sent_fb': ('civilian', 'magma'), 'astral_sk': None})[0] != got:
        fails.append('side_end_at_markers is not idempotent')
    if not side_end_at_markers(['# ( "XML1 endSideMission from side mission sent_fb" )', 'foo( )'],
                               {'sent_fb': ('default', '')})[2]:
        fails.append('side_end_at_markers accepted a marker without its loadZone')
    pop = pop_block('', 'civilian', 'magma', 'mansion/man2/subbasement2')
    if _run_forced(pop)[0] != ['debug', 'setSkinset', 'popParty'] or \
            _run_forced(pop, dll=False)[0] != ['loadMapChooseTeam'] or _run_forced(pop, features=())[0] != ['loadMapChooseTeam']:
        fails.append('pop block runtime')
    # join: addHero branch (AddHero=1 and success) / joinHero (JoinHero on: 1 queued, 2 in the party already) /
    # T7 (both off, no DLL, both failed); the popup and its wait before every branch
    src = ['waittimed ( 1.000 )', 'unlockCharacter("cyclops", "" )', 'unlockCharacter("cyclops", "" )',
           'extractionPointLite("_ACTIVE_HERO_", "true", "false", "false" )', 'createPopupDialogXml("dialogs/tut15" )']
    got, heroes, pops = join_hero(src, 1, add_hero=True)
    blk = join_block('', 'cyclops', 1, add_hero=True)
    if got != ['waittimed ( 1.000 )', JOIN_POPUP_COMMENT, 'createPopupDialogXml("dialogs/tut15" )',
               'waittimed ( 0.500 )'] + blk or heroes != ['cyclops'] or pops != ['dialogs/tut15'] or \
            join_hero(got, 1, add_hero=True) != (got, [], []):
        fails.append(f'join_hero(add_hero): {got}')
    if blk[:2] != ['unlockCharacter("cyclops", "" )', 'setGameFlag("x1join", 1, 1 )']:
        fails.append('join_hero(add_hero): the join bit is not set before the branches')
    t7 = ['remove', 'extractionPointChange']
    jh = (FT_FEATURE, JH_FEATURE)
    cases = [(dict(features=(FT_FEATURE, AH_FEATURE, JH_FEATURE)), ['remove']),
             (dict(features=jh), ['debug', 'remove']),
             (dict(features=jh, join_hero_ok=2), ['debug', 'remove']),
             (dict(features=jh, join_hero_ok=0), ['debug', 'remove'] + t7),
             (dict(features=(FT_FEATURE, AH_FEATURE, JH_FEATURE), add_hero_ok=0), ['remove', 'debug', 'remove']),
             (dict(features=(FT_FEATURE, AH_FEATURE), add_hero_ok=0), ['remove', 'debug'] + t7),
             (dict(features=(FT_FEATURE,)), ['debug'] + t7),
             (dict(dll=False), ['debug'] + t7)]
    for kw, want_calls in cases:
        flags = {}
        calls, _ = _run_forced(blk, flags=flags, **kw)
        if calls != ['unlockCharacter'] + want_calls or flags != {('x1join', 1): 1}:
            fails.append(f'join block runtime {kw}: {calls} {flags}')
    dropped = _drop_xml2fix(blk)
    if dropped[dropped.index('if x1ah == 0') + 1] != '     ' + FT_KEEP:
        fails.append('join block: the joinhero query branch is empty without the DLL')
    jk = blk.index('     x1ah = joinHero("cyclops" )')
    if blk[jk - 1] != '     remove ( "cyclops_x1double", "cyclops_x1double" )' or blk[jk + 1] != 'endif':
        fails.append('join block: joinHero is not after the double\'s remove and last in its branch')
    # guard rule (V14b): every generated block passes; the negative cases are caught
    for name, block in (('seat', seat), ('skinset', skin), ('push', push_block()), ('pop', pop), ('join', blk)):
        p = xml2fix_guard_problems(block)
        if p:
            fails.append(f'xml2fix_guard_problems flags the {name} block: {p}')
    bad = {'undeclared': ['x1ft = xml2fixFeature("forcedteams" )', 'if x1ft == 1', '     seatParty("magma", "", "", "" )',
                          'endif'],
           'unguarded': ['setSkinset("default", "" )'],
           'else branch': seat[:4] + ['     loadMapKeepTeam("z" )', 'else', '     popParty("z" )', 'endif'],
           'wrong feature': ['x1ah = iadd(0, 0 )', 'x1ah = xml2fixFeature("addhero" )', 'if x1ah == 1',
                             '     seatParty("magma", "", "", "" )', 'endif'],
           'addHero outside its guard': seat[1:4] + ['     x1ah = addHero("cyclops" )', 'endif'],
           'joinHero behind the addhero guard': ['x1ah = iadd(0, 0 )', 'x1ah = xml2fixFeature("addhero" )',
                                                 'if x1ah == 1', '     x1ah = joinHero("cyclops" )', 'endif'],
           'unknown feature': ['x1ft = iadd(0, 0 )', 'x1ft = xml2fixFeature("forced" )'],
           'bare query': ['xml2fixFeature("forcedteams" )']}
    for name, lines in bad.items():
        if not xml2fix_guard_problems(lines):
            fails.append(f'xml2fix_guard_problems missed the {name} case')
    # team lock: after every begin marker (1 forced, 0 other), before a side mission's end marker (the caller's)
    src = ['# Generated by rewrite_scripts.py', '# ( "XML1 beginMission(mansion1)" )', 'setCurrentAct(1 )',
           'if x == 1', '     # ( "XML1 beginMission(haarp)" )', '     setCurrentAct(1 )', 'endif',
           '# ( "XML1 beginMission(other)" )']
    got, done = team_lock_at_markers(src, {'mansion1': 1, 'haarp': 0})
    want = src[:2] + [TEAM_LOCK_COMMENT, 'setGameFlag("teamlock", 1, 1 )'] + src[2:5] + \
        ['     ' + TEAM_LOCK_COMMENT, '     setGameFlag("teamlock", 1, 0 )'] + src[5:]
    if got != want or done != [('mansion1', 1), ('haarp', 0)] or team_lock_at_markers(got, {'mansion1': 1, 'haarp': 0}) != (got, []):
        fails.append(f'team_lock_at_markers: {got} {done}')
    end = ['if iDone == 1', '     waittimed ( 1.000 )', '     # ( "XML1 endSideMission from side mission sent_fb" )',
           '     setCurrentAct(1 )', '     loadZone("mansion/man2/mansion2_1", "" )', 'endif',
           '# ( "XML1 endSideMission from side mission astral_sk" )', 'loadZone("astral/savepx/astral2_3", "" )']
    got, done = team_lock_at_side_ends(end, {'sent_fb': 1, 'astral_sk': 0})
    want = end[:2] + ['     ' + TEAM_LOCK_RETURN_COMMENT, '     setGameFlag("teamlock", 1, 1 )'] + end[2:6] + \
        [TEAM_LOCK_RETURN_COMMENT, 'setGameFlag("teamlock", 1, 0 )'] + end[6:]
    if got != want or done != [('sent_fb', 1), ('astral_sk', 0)] or team_lock_at_side_ends(got, {'sent_fb': 1}) != (got, []):
        fails.append(f'team_lock_at_side_ends: {got} {done}')
    # the pop still follows its marker: side_end_at_markers on the locked text rewrites the same sites
    popped, pdone, pprobs = side_end_at_markers(got, {'sent_fb': ('civilian', 'magma'), 'astral_sk': None})
    if pprobs or [k for _, _, k in pdone] != ['pop', 'menu']:
        fails.append(f'side_end_at_markers after the team lock: {pdone} {pprobs}')
    for v in (1, 0):
        flags = {(TEAM_LOCK_FLAG, TEAM_LOCK_BIT): 1 - v}
        run_pack_ops([team_lock_line(v)], flags)
        if flags != {(TEAM_LOCK_FLAG, TEAM_LOCK_BIT): v}:
            fails.append(f'team lock line runtime: {team_lock_line(v)} -> {flags}')
    return fails
