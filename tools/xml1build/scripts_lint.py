"""xml1build.scripts_lint - offline mirror of XMen2.exe's per-line script checks (private helper of scripts.py).

XMen2.exe splits a script file on CRLF (0x4a1290) and parses every line on its own (0x4d9740). A statement
whose function is not registered (EXACT case: 0x4d6910 interns the token with a raw-byte hash and compares
with repe cmpsb), whose argument count differs from len(argsig), or whose literal / bound-variable type is
wrong (type table 0x4d8ad4: 'i'/'f' need a number, 's' needs a string, anything else accepts anything) is
silently DROPPED (0x4da37a; the caller loop 0x4da511 ignores the failure). Keywords (if / elif / elseif /
else / endif / def) and variable names are compared with _stricmp; a 'game.' prefix is discarded; lines with
__name__ and calls to main() are skipped (0x4d9937 / 0x4d9cf2).

Inline data scripts (an attribute value containing '(', 0x4a11f9) are copied into a 255-byte buffer
(0x4a12b5) and split on the literal 4 characters \\n\\r (0x68d348). Code run through the console as
'runscript <code>' (dialog options 0x5eb8e3, blackbird menu 0x5e08d4) is tokenised on whitespace and ';'
(0x55b670), and the console queue copies at most 127 characters (0x55c42f).

Ported from research/scripts/verify/v_output.py (independent validator) with EXACT-case name matching, as
the scripts VERIFICATION section requires. Pure functions; `api` is ctx.xml2_api (name -> {args, ret}).
"""
from __future__ import annotations

import re

BLOCK_KEYWORDS = ('if', 'elif', 'elseif', 'else', 'endif')
OPS = ('==', '!=', '<=', '>=', '<', '>')
NUM = re.compile(r'^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$')
IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
CALLRE = re.compile(r'^([A-Za-z_][A-Za-z0-9_.]*)\s*\((.*)\)\s*$', re.S)
ASSIGNRE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)\s*(.*)$', re.S)
INLINE_SEP = '\\n\\r'            # the literal 4 characters backslash n backslash r (0x68d348)
INLINE_MAX = 255                 # strncpy(buf, src, 0xff) at 0x4a12b5
CONSOLE_MAX = 127                # console queue strncpy 0x80 at 0x55c42f (includes the 'runscript ' prefix)
RUNSCRIPT = 'runscript '
ENTITY_TOKENS = ('_owner_', '_activator_')     # accepted bare by v_output.py (research verifier)


def strip_comment(line: str) -> str:
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
            continue
        if ch in '"\'':
            q = ch
        elif ch == '#':
            return line[:i]
    return line


def split_args(s: str):
    out, cur, q, depth = [], '', None, 0
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
            continue
        if ch in '"\'':
            q = ch
            cur += ch
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip())
            cur = ''
            continue
        cur += ch
    if cur.strip() or out:
        out.append(cur.strip())
    return out


def literal_value(a: str):
    """'"abc"' / "'abc'" -> 'abc'; anything else -> None."""
    if len(a) >= 2 and a[0] in '"\'' and a[-1] == a[0]:
        return a[1:-1]
    return None


def argkind(a: str, vars_: dict) -> str:
    if literal_value(a) is not None:
        return 's'
    if NUM.match(a):
        return 'n'
    if IDENT.match(a):
        la = a.lower()
        if la in vars_:
            return 'v:' + vars_[la]
        if la in ENTITY_TOKENS:
            return 'ent'
        return 'undef'
    if '(' in a:
        return 'call'
    return 'other'


# registered in XMen2.exe but no-ops / XML1-only semantics: converted XML1 code must not call them (XML2
# beginMission/beginMissionHack/loadMap send console commands XMen2.exe never registers; the mission-var and
# screenFade calls are not registered at all). Compared case-insensitively.
FORBIDDEN_IN_X1 = ('beginmission', 'beginmissionhack', 'loadmap', 'setmissionvar', 'getmissionvar', 'screenfade',
                   'beginsidemission', 'endsidemission', 'setmissionflag', 'getmissionflag')


def check_call(name: str, args, vars_, api, forbidden=True):
    """-> (ret_sig or None, [problem strings]). forbidden=False when checking against XML1's own table."""
    n = name[5:] if name.startswith('game.') else name
    if forbidden and n.lower() in FORBIDDEN_IN_X1:
        return None, [f'XML1-only / no-op call {name} left in converted code']
    e = api.get(n)
    if e is None:
        low = {k.lower(): k for k in api}
        if n.lower() in low:
            return None, [f'wrong case: {name} (registered as {low[n.lower()]})']
        return None, [f'unregistered function {name}']
    sig = e['args']
    if len(args) != len(sig):
        return e['ret'], [f'{n}: argc {len(args)} != {len(sig)} ({sig!r})']
    probs = []
    for a, t in zip(args, sig):
        k = argkind(a, vars_)
        if k == 'call':
            probs.append(f'{n}: nested call argument {a}')
        elif t in 'if' and k in ('s', 'v:s'):
            probs.append(f'{n}: string for {t} parameter: {a}')
        elif t == 's' and k in ('n', 'v:i', 'v:f'):
            probs.append(f'{n}: number for s parameter: {a}')
    return e['ret'], probs


def iter_statements(lines):
    """yield (lineno, statement_text) for every non-blank, non-comment line (comments stripped)."""
    for i, line in enumerate(lines, 1):
        s = strip_comment(line).strip()
        if s:
            yield i, s


def lint_lines(lines, api, forbidden=True):
    """Check a list of script lines like XMen2.exe would. Returns (problems, info):
    problems = [(lineno, kind, detail)], info = {'statements': n, 'calls': [(lineno, name, [args])]}."""
    problems, calls = [], []
    vars_ = {}
    depth = 0
    n_stmt = 0
    for ln, s in iter_statements(lines):
        n_stmt += 1
        first = re.split(r'[\s(:]', s, 1)[0].lower()
        if first in ('if', 'elif', 'elseif'):
            if first == 'if':
                depth += 1
            cond = s[len(first):].strip().rstrip(':').strip()
            op = next((o for o in OPS if o in cond), None)
            if op is None:
                problems.append((ln, 'condition', f'no comparison in {s!r}'))
                continue
            left, right = [x.strip() for x in cond.split(op, 1)]
            for a in (left, right):
                k = argkind(a, vars_)
                if k in ('undef', 'call', 'other'):
                    problems.append((ln, 'condition', f'operand {a!r} is {k}'))
            continue
        if first in ('else', 'endif'):
            if first == 'endif':
                depth -= 1
                if depth < 0:
                    problems.append((ln, 'block', 'endif without if'))
                    depth = 0
            continue
        if first in ('def', 'import', 'from') or '__name__' in s:
            continue                    # skipped by the engine
        m = ASSIGNRE.match(s)
        if m:
            tgt, rhs = m.group(1), m.group(2).strip()
            mc = CALLRE.match(rhs)
            if not mc:
                problems.append((ln, 'assign', f'assignment of a non-call: {s!r}'))
                vars_[tgt.lower()] = 'n'
                continue
            args = split_args(mc.group(2))
            ret, probs = check_call(mc.group(1), args, vars_, api, forbidden)
            calls.append((ln, mc.group(1), args))
            problems += [(ln, 'call', p) for p in probs]
            vars_[tgt.lower()] = ret or '?'
            continue
        mc = CALLRE.match(s)
        if mc:
            name = mc.group(1)
            if name.lower() in ('main', 'game.main'):
                continue                # skipped by the engine (0x4d9cf2)
            args = split_args(mc.group(2))
            calls.append((ln, name, args))
            _, probs = check_call(name, args, vars_, api, forbidden)
            problems += [(ln, 'call', p) for p in probs]
            continue
        problems.append((ln, 'unparsed', s))
    if depth != 0:
        problems.append((0, 'block', f'if/endif imbalance {depth:+d}'))
    return problems, {'statements': n_stmt, 'calls': calls}


def lint_script_bytes(data: bytes, api):
    """Lint a whole script file (bytes). Adds line-ending problems (the engine splits on CRLF only)."""
    problems = []
    if b'\0' in data:
        problems.append((0, 'bytes', 'NUL byte'))
    text = data.decode('latin-1')
    if '\n' in text.replace('\r\n', '') or '\r' in text.replace('\r\n', ''):
        problems.append((0, 'eol', 'bare LF or CR (XMen2.exe splits on CRLF, 0x4a1290)'))
    lines = text.split('\r\n')
    probs, info = lint_lines(lines, api)
    return problems + probs, info


def split_inline(code: str):
    """inline data script -> statements (split on the literal \\n\\r like 0x68d348)."""
    return [p for p in code.split(INLINE_SEP)]


def lint_inline(code: str, api, forbidden=True):
    """Problems of one inline data script: size (255-byte buffer) and every statement."""
    problems = []
    if len(code.encode('latin-1', 'replace')) > INLINE_MAX:
        problems.append((0, 'size', f'inline script is {len(code)} bytes (> {INLINE_MAX}, truncated at 0x4a12b5)'))
    probs, info = lint_lines(split_inline(code), api, forbidden)
    return problems + probs, info


def console_problems(code: str):
    """Constraints on code run as 'runscript <code>' (dialog options, blackbird menu)."""
    out = []
    if re.search(r'[\s;]', code):
        out.append('contains whitespace or ";" (console tokenizer 0x55b670 splits there)')
    if len(RUNSCRIPT + code) > CONSOLE_MAX:
        out.append(f'"runscript {code}" is {len(RUNSCRIPT + code)} chars (> {CONSOLE_MAX}, console queue 0x55c42f)')
    return out


# Script functions that send a console command (research/scripts/verify/console_senders.json, extracted from
# the XMen2.exe registrations that reach the console object 0x7ac290). The console queue (0x55c410) refuses a
# command when 2 are already pending ([+0x630] == 2 -> return 0, 0x55c426), and it is pumped between script
# ticks, so more than 2 sends with no waittimed/waitsignal in between drop the extra commands silently.
CONSOLE_SENDERS_DEFAULT = (
    'Logout', 'SetDontShowWarningOff', 'beginMission', 'beginMissionHack', 'blackbirdMenu', 'closemenu',
    'codexMenu', 'dangerRoomEndMission', 'dangerRoomMenu', 'endDRScenario', 'extractionPointChange', 'loadMap',
    'loadMapAddTeam', 'loadMapChooseTeam', 'loadMapKeepTeam', 'mainMenuExit', 'mainMenuExitDialog', 'openmenu',
    'personalItem', 'restartZone', 'restorelastzone', 'reviewCinematics', 'reviewComics', 'reviewConcept',
    'reviewLoadScreens', 'reviewMenu', 'setDifficultyLevel', 'setupHost', 'shopMenu', 'startFirstMission',
    'startGameDiffDialog', 'startMovie', 'startMoviePreview', 'stashMenu', 'triviaMenu', 'useDefaultStats',
    'viewSparringHighScores')
XML2FIX_CONSOLE_SENDERS = ('popParty', 'joinHero')  # xml2-fix (SPEC 19): queue restorelastzone 0 / loadmap <z> 0 1
CONSOLE_PENDING_MAX = 2
WAIT_FUNCS = ('waittimed', 'waitsignal')
_CALLNAME = re.compile(r'^(?:[A-Za-z_][A-Za-z0-9_]*\s*=(?!=)\s*)?([A-Za-z_][A-Za-z0-9_.]*)\s*\(')


def console_overflows(lines, senders=CONSOLE_SENDERS_DEFAULT, limit=CONSOLE_PENDING_MAX):
    """Branch-aware count of console commands a script queues with no wait in between.

    Walks the if/elif/else/endif structure keeping the set of possible 'sends since the last wait' values
    along every path (exclusive branches are not added together). Returns [(lineno, function, count)] for
    every send that can make more than `limit` commands pending."""
    snd = {s.lower() for s in senders}
    waits = set(WAIT_FUNCS)
    cur = {0}
    stack = []                              # frames: [entry_set, outs_set, has_else]
    out = []
    for ln, s in iter_statements(lines):
        first = re.split(r'[\s(:]', s, 1)[0].lower()
        if first == 'if':
            stack.append([set(cur), set(), False])
            continue
        if first in ('elif', 'elseif', 'else'):
            if stack:
                fr = stack[-1]
                fr[1] |= cur
                cur = set(fr[0])
                if first == 'else':
                    fr[2] = True
            continue
        if first == 'endif':
            if stack:
                entry, outs, has_else = stack.pop()
                outs |= cur
                if not has_else:
                    outs |= entry
                cur = outs or {0}
            continue
        m = _CALLNAME.match(s)
        if not m:
            continue
        n = m.group(1)
        n = (n[5:] if n.lower().startswith('game.') else n).lower()
        if n in waits:
            cur = {0}
        elif n in snd:
            cur = {min(r + 1, 99) for r in cur}
            worst = max(cur)
            if worst > limit:
                out.append((ln, m.group(1), worst))
    return out


# roster flow (research/heroes/roster.md T13): loadMapAddTeam sends "resetgame" then an unregistered command
# (0x4a0bf8 / 0x4a0c07): it resets the whole game and loads nothing. extractionPointLite("_ACTIVE_HERO_", ...)
# shows only the hint dialog while game flag danv bit 1 is clear (0x4a6e3e-0x4a6e63): as an addHero emulation it
# must be preceded by setGameFlag("danv", 1, 1) (or replaced by the T7 join_hero pattern).
_DANV_SET = re.compile(r'''setGameFlag\(\s*["']danv["']\s*,\s*1\s*,\s*1\s*\)''')


def roster_problems(lines):
    """[(lineno, kind, detail)] for the roster-flow rules T13 over a script's lines."""
    out = []
    danv = False
    for ln, s in iter_statements(lines):
        if _DANV_SET.search(s):
            danv = True
        m = _CALLNAME.match(s)
        if not m:
            continue
        n = m.group(1)
        n = n[5:] if n.lower().startswith('game.') else n
        if n.lower() == 'loadmapaddteam':
            out.append((ln, 'roster', 'loadMapAddTeam sends "resetgame" + an unregistered command (0x4a0bf8): never emit it'))
        elif n.lower() == 'extractionpointlite' and re.search(r'''\(\s*["']_ACTIVE_HERO_["']''', s) and not danv:
            out.append((ln, 'roster', 'extractionPointLite("_ACTIVE_HERO_", ...) without a preceding setGameFlag("danv", 1, 1): '
                                      'only the hint dialog shows (0x4a6e3e); use the T7 join_hero pattern'))
    return out


def compact(stmt: str) -> str:
    """drop whitespace outside quoted strings (research/scripts/rewrite_scripts.compact)."""
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
