"""xml1build.validate_script - offline model of XMen2.exe's BehavEd script line parser, for validate V7/V10.

Engine facts modelled (research/_summaries/scripts.md, VERIFICATION section wins):
  * script files are split on CRLF (0x4a1290, separator 0x68d350); a bare LF or CR merges lines.
  * each line is parsed on its own (0x4d9740): '#' comments, " or ' quoted strings, keywords
    if / elif / elseif / else / endif / def compared with _stricmp, 'def' lines and lines containing
    '__name__' or calling main() are skipped, a 'game.' prefix on a call is discarded.
  * the FUNCTION NAME lookup is case-sensitive: 0x4d8970 -> 0x4d6910 interns the token with a raw-byte hash
    (0x41a340) and an exact 'repe cmpsb' (0x419d0b). research's verify_output.py / validate_lines matched
    case-insensitively and would hide mis-cased calls; this module matches exactly.
  * a line whose function is unknown, whose argc != len(argsig) (0x4d89c3) or whose literal type does not fit
    the signature letter (type table 0x4d8ad4: 'i'/'f' need a number, 's' needs a string, anything else
    accepts any) is freed and silently DROPPED; the rest of the script still runs (0x4da511..0x4da536).
    The type check also applies to script variables through their bound kind (0x4d8a3c).
  * inline data scripts: an attribute value containing '(' is code (0x4a11f9), copied into a 255-byte buffer
    (0x4a12b5 strncpy 0xff) and split on the literal 4 characters \\n\\r (0x68d348).
  * console commands (dialog option 'runscript <code>', blackbirdMenu 'setblackbirdparms %s %s %s FALSE
    FALSE'): the tokenizer (0x55b670) splits on whitespace (<= 0x20) and ';', the queue copies at most 127
    characters (0x55c42f strncpy 0x80) and drops a command when 2 are already pending (0x55c426);
    setblackbirdparms tokens go into 64-byte buffers (0x5f2408).
  * engine pools: 620 statement nodes (0x4d7e6e), 1556 int/float values (0x4d6578), 120 script objects
    (0x4d86d1); whether they are per zone is unverified (validate only warns).

Severity policy: 'error' = the engine provably drops or mis-parses the line (unknown / mis-cased function,
argc, literal or bound-variable type mismatch, bare LF/CR, if/endif imbalance, XML1 functions XML2 does not
have). 'warn' = syntax XML2 retail scripts never use and whose engine behaviour is unverified (a call inside
an if condition, nested calls as arguments, expressions, an undefined identifier as argument, a literal
assignment, text after ')', an unparsable statement).

Pure module: no file writes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

KEYWORDS = {'if', 'elif', 'elseif', 'else', 'endif', 'def'}
COND_OPS = ('==', '!=', '<=', '>=', '<', '>')
INLINE_SEP = '\\n\\r'                 # the literal 4 characters backslash n backslash r (0x68d348)
INLINE_MAX = 255                      # 0x4a12b5 strncpy(buf, src, 0xff)
CONSOLE_MAX = 127                     # 0x55c42f strncpy(.., 0x80) incl. NUL
BLACKBIRD_TOKEN_MAX = 63              # 0x5f2408: 64-byte token buffers
NODE_POOL = 620                       # 0x4d7e6e
VALUE_POOL = 1556                     # 0x4d6578 cmp 0x614
SCRIPT_OBJECTS = 120                  # 0x4d86d1
GAME_STORE_NAMES = 100                # 0x4d7130 count < 0x64
GAME_STORE_NAMELEN = 11               # 0x4d7130 len < 0xc
ZONE_STORE_NAMES = 32                 # 0x4d7060 count < 0x20
ZONE_STORE_NAMELEN = 11               # 0x4d7060 len < 0xc
ENGINE_GAME_FLAGS = ('danv', 'r_d_disc', 'r_imarmor', 'r_t_station')   # pushes before 0x4a1670

# XML1 script API the XML1 output must never call (no-ops or unregistered in XMen2.exe; SPEC 4.3)
FORBIDDEN_IN_X1 = {
    'beginMission': "XML2 beginMission sends the unregistered console command 'beginmission' (no-op)",
    'beginMissionHack': "XML2 beginMissionHack sends the unregistered 'beginmissionhack' (no-op)",
    'loadMap': "XML2 loadMap sends the unregistered 'loadmapaddteam' (no-op); XML1 loadMap == loadMapKeepTeam",
    'setMissionVar': 'XML1-only (not registered in XMen2.exe); mission vars are packed into game flags',
    'getMissionVar': 'XML1-only (not registered in XMen2.exe); mission vars are packed into game flags',
    'screenFade': 'XML1-only alias of cameraFade (not registered in XMen2.exe)',
}
# functions whose handler sends a console command (queue holds at most 2 pending commands, 0x55c426)
CONSOLE_SENDERS = {'startMovie', 'blackbirdMenu', 'loadMap', 'loadMapKeepTeam', 'loadMapChooseTeam',
                   'loadMapAddTeam', 'loadZone', 'beginMission', 'beginMissionHack', 'restorelastzone',
                   'extractionPointChange',
                   'popParty',               # xml2-fix (SPEC 19): queues restorelastzone 0 / loadmap <z> 0 1
                   'joinHero'}               # xml2-fix (SPEC 19.6): queues restorelastzone 0
WAITS = {'waittimed', 'waitsignal'}
# A popup (createPopupDialogXml, 0x4a6890 -> the popup manager 0x5eb300 vt+0x64) stays up until the player closes
# it; no wait closes it and no script function waits for it. Pending under the team menu it broke the menu in game
# (2026-09-28, nyc1_1_3's join: after one Enter the hint bar dropped to "Details / Accept", Replace/Details stopped
# responding; the likeliest cause of Owen's pad-B hang), and a reload or menu must not have one pending. A waittimed
# runs out only once the player has closed the popup (the game pauses; in game the same night: the next statement
# ran 0.4 s after the close), so no call that opens a menu or reloads may follow a popup on any path through the
# same script (if / else branches apart) without a waittimed between them.
POPUP_CALLS = {'createPopupDialogXml', 'createPopupDialogXmlFilter'}
POPUP_BLOCKERS = {'extractionPointChange', 'extractionPointLite', 'joinHero', 'popParty', 'blackbirdMenu',
                  'loadMap', 'loadMapKeepTeam', 'loadMapChooseTeam', 'loadMapAddTeam', 'loadZone', 'restorelastzone',
                  'beginMission', 'beginMissionHack', 'openmenu', 'shopMenu', 'stashMenu', 'codexMenu', 'reviewMenu',
                  'dangerRoomMenu', 'triviaMenu', 'startGameDiffDialog', 'mainMenuExit', 'mainMenuExitDialog'}
LOAD_FUNCS = ('loadMapKeepTeam', 'loadMapChooseTeam', 'loadMapAddTeam', 'loadMap', 'loadZone')

TOKEN_RE = re.compile(r'''
    (?P<ws>[ \t]+)
  | (?P<str>"[^"]*"|'[^']*')
  | (?P<num>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)
  | (?P<op>==|!=|<=|>=|<|>|=|\+|-|\*|/|%)
  | (?P<punct>[(),:\[\]])
  | (?P<comment>\#.*)
  | (?P<bad>.)
''', re.X)
NUM_RE = re.compile(r'^[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?$')


@dataclass
class Arg:
    kind: str            # 'str' | 'num' | 'ident' | 'call' | 'expr' | 'empty'
    text: str
    value: object = None


@dataclass
class Call:
    name: str            # as written, 'game.' prefix removed
    args: list
    line: int
    trailing: str = ''
    prefix: str = ''
    text: str = ''       # the whole statement as written (stripped)


@dataclass
class Problem:
    severity: str        # 'error' | 'warn'
    line: int
    kind: str
    msg: str
    func: str = ''       # function concerned (allowlists match on it)
    call: object = None  # the Call for call-level problems (validate re-checks it against XML1's own API)

    def text(self, where):
        return f'{where}:{self.line}: {self.kind}: {self.msg}' if self.line else f'{where}: {self.kind}: {self.msg}'


@dataclass
class ScriptResult:
    statements: int = 0                       # non-blank, non-comment lines (one pool node each)
    literals: int = 0                         # string + numeric literals (value pool)
    calls: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    def errors(self):
        return [p for p in self.problems if p.severity == 'error']

    def warnings(self):
        return [p for p in self.problems if p.severity == 'warn']

    def literal_args(self, func, index):
        """string/number literal values of argument `index` of every call to `func` (exact case)."""
        return [c.args[index].value for c in self.calls
                if c.name == func and len(c.args) > index and c.args[index].kind in ('str', 'num')]


def tokenize(s):
    return [(m.lastgroup, m.group()) for m in TOKEN_RE.finditer(s) if m.lastgroup != 'ws']


def _make_arg(toks):
    text = ''.join(t[1] for t in toks)
    if not toks:
        return Arg('empty', '')
    if len(toks) == 1:
        k, v = toks[0]
        if k == 'str':
            return Arg('str', v, v[1:-1])
        if k == 'num':
            return Arg('num', v, v)
        if k == 'ident':
            return Arg('ident', v, v)
    if len(toks) == 2 and toks[0][0] == 'op' and toks[0][1] in '+-' and toks[1][0] == 'num':
        return Arg('num', text, text)
    if toks[0][0] == 'ident' and len(toks) >= 3 and toks[1] == ('punct', '('):
        try:
            args, j = _parse_args(toks, 1)
            if j == len(toks):
                return Arg('call', text, (toks[0][1], args))
        except ValueError:
            pass
    return Arg('expr', text)


def _parse_args(toks, i):
    """toks[i] is '('; returns (args, index after the matching ')')."""
    i += 1
    args, cur, depth = [], [], 0
    while i < len(toks):
        t = toks[i]
        if t == ('punct', '('):
            depth += 1
        elif t == ('punct', ')'):
            if depth == 0:
                if cur or args:
                    args.append(_make_arg(cur))
                return args, i + 1
            depth -= 1
        elif t == ('punct', ',') and depth == 0:
            args.append(_make_arg(cur))
            cur = []
            i += 1
            continue
        cur.append(t)
        i += 1
    raise ValueError('unterminated (')


def _P(func, severity, line, kind, msg):
    return Problem(severity, line, kind, msg, func)


def _split_prefix(ident):
    """'game.cameraReset' -> ('game.', 'cameraReset'); the engine discards only the 'game.' prefix."""
    if ident[:5].lower() == 'game.':
        return ident[:5], ident[5:]
    return '', ident


class ScriptChecker:
    """Checks BehavEd statements against XMen2.exe's registration table (ctx.xml2_api, exact case)."""

    def __init__(self, api):
        self.api = dict(api)
        self.by_lower = {}
        for k in self.api:
            self.by_lower.setdefault(k.lower(), k)

    # ------------------------------------------------------------------------------------------ calls
    def _check_call(self, res, call, vars_, x1_output):
        n0 = len(res.problems)
        ret = self._check_call_inner(res, call, vars_, x1_output)
        for p in res.problems[n0:]:
            p.call = call
        return ret

    def signature_problem(self, call):
        """'unknown' / 'argc' / 'type' / None: whether `call` would be dropped by an engine with this checker's
        registration table (used with XML1's table to recognise inherited, already-dropped lines)."""
        entry = self.api.get(call.name)
        if entry is None:
            return 'unknown'
        sig = entry.get('args', '')
        if len(call.args) != len(sig):
            return 'argc'
        for a, t in zip(call.args, sig):
            if (t in ('i', 'f') and a.kind == 'str') or (t == 's' and a.kind == 'num'):
                return 'type'
        return None

    def _check_call_inner(self, res, call, vars_, x1_output):
        name = call.name
        entry = self.api.get(name)
        if entry is None:
            right = self.by_lower.get(name.lower())
            if right is not None:
                res.problems.append(_P(name, 'error', call.line, 'wrong case',
                                            f'{name}(): registered as {right!r}; lookup is case-sensitive'))
            else:
                res.problems.append(_P(name, 'error', call.line, 'unknown function',
                                            f'{name}() is not registered in XMen2.exe'))
            if x1_output and name in FORBIDDEN_IN_X1:
                res.problems.append(_P(name, 'error', call.line, 'forbidden', f'{name}(): {FORBIDDEN_IN_X1[name]}'))
            return None
        if x1_output and name in FORBIDDEN_IN_X1:
            res.problems.append(_P(name, 'error', call.line, 'forbidden', f'{name}(): {FORBIDDEN_IN_X1[name]}'))
        sig = entry.get('args', '')
        if len(call.args) != len(sig):
            res.problems.append(_P(name, 'error', call.line, 'argc',
                                        f'{name}() takes {len(sig)} args ({sig!r}), got {len(call.args)}'))
            return entry.get('ret')
        for i, (a, t) in enumerate(zip(call.args, sig)):
            k = a.kind
            if k == 'ident':
                vk = vars_.get(a.text.lower())
                if vk is None:
                    res.problems.append(_P(name, 'warn', call.line, 'undefined identifier',
                                                f'{name}() arg {i + 1} {a.text!r} is not an assigned variable'))
                    continue
                if t in ('i', 'f') and vk == 's':
                    res.problems.append(_P(name, 'error', call.line, 'type',
                                                f'{name}() arg {i + 1} {a.text!r} is a string variable, sig {t!r}'))
                elif t == 's' and vk in ('i', 'f'):
                    res.problems.append(_P(name, 'error', call.line, 'type',
                                                f'{name}() arg {i + 1} {a.text!r} is a number variable, sig s'))
                continue
            if k == 'call':
                res.problems.append(_P(name, 'warn', call.line, 'nested call',
                                            f'{name}() arg {i + 1} is a call ({a.text}); XML2 retail never does this'))
                continue
            if k in ('expr', 'empty'):
                res.problems.append(_P(name, 'warn', call.line, 'expression',
                                            f'{name}() arg {i + 1} {a.text!r} is not a literal or variable'))
                continue
            if t in ('i', 'f') and k == 'str':
                res.problems.append(_P(name, 'error', call.line, 'type',
                                            f'{name}() arg {i + 1} is a string literal {a.text}, sig {t!r} needs a number'))
            elif t == 's' and k == 'num':
                res.problems.append(_P(name, 'error', call.line, 'type',
                                            f'{name}() arg {i + 1} is a number literal {a.text}, sig s needs a string'))
        return entry.get('ret')

    # ------------------------------------------------------------------------------------------ lines
    def _statement(self, res, no, raw, state, x1_output):
        s = raw.strip(' \t')
        if not s or s.startswith('#'):
            return
        if '\x00' in s:
            res.problems.append(Problem('error', no, 'nul', 'NUL byte in line'))
        toks = tokenize(s)
        if toks and toks[-1][0] == 'comment':
            toks = toks[:-1]
        if not toks:
            return
        res.statements += 1
        res.literals += sum(1 for t in toks if t[0] in ('str', 'num'))
        bad = [t[1] for t in toks if t[0] == 'bad']
        if '__name__' in s:
            return                                   # skipped by the engine (0x4d9937)
        first = toks[0]
        if first[0] == 'ident' and first[1].lower() in KEYWORDS:
            kw = first[1].lower()
            if kw == 'def':
                return                               # 'def' lines are skipped by the engine
            if kw == 'if':
                state['depth'] += 1
            elif kw == 'endif':
                state['depth'] -= 1
                if state['depth'] < 0:
                    res.problems.append(Problem('error', no, 'if/endif', 'endif without if'))
                    state['depth'] = 0
            elif state['depth'] == 0:
                res.problems.append(Problem('error', no, 'if/endif', f'{kw} outside an if block'))
            # the popup pending along this path (POPUP_BLOCKERS): exclusive branches are not added together
            frames = state.setdefault('popup_frames', [])
            if kw == 'if':
                frames.append([state.get('popup'), None])
            elif kw in ('elif', 'elseif', 'else') and frames:
                frames[-1][1] = frames[-1][1] or state.get('popup')
                state['popup'] = frames[-1][0]
            elif kw == 'endif' and frames:
                entry, merged = frames.pop()
                state['popup'] = state.get('popup') or merged or entry
            state['console_run'] = 0
            if kw in ('if', 'elif', 'elseif'):
                rest = toks[1:]
                if rest and rest[-1] == ('punct', ':'):
                    rest = rest[:-1]
                ops = [i for i, t in enumerate(rest) if t[0] == 'op' and t[1] in COND_OPS]
                if len(ops) != 1:
                    res.problems.append(Problem('warn', no, 'condition', f'{s!r}: not "<a> <op> <b>"'))
                    return
                k = ops[0]
                for side in (rest[:k], rest[k + 1:]):
                    a = _make_arg(side)
                    if a.kind == 'call':
                        res.problems.append(Problem('warn', no, 'call in condition',
                                                    f'{s!r}: XML2 retail conditions only compare variables/literals'))
                    elif a.kind == 'ident' and a.text.lower() not in state['vars']:
                        res.problems.append(Problem('warn', no, 'undefined identifier',
                                                    f'{s!r}: {a.text!r} is not an assigned variable'))
                    elif a.kind in ('expr', 'empty'):
                        res.problems.append(Problem('warn', no, 'condition', f'{s!r}: operand {a.text!r}'))
            return
        if bad:
            res.problems.append(Problem('warn', no, 'syntax', f'unexpected characters {bad!r} in {s!r}'))
        target = None
        if first[0] == 'ident' and len(toks) >= 3 and toks[1] == ('op', '='):
            target = first[1]
            toks = toks[2:]
            if not (toks and toks[0][0] == 'ident' and len(toks) >= 3 and toks[1] == ('punct', '(')):
                a = _make_arg(toks)
                res.problems.append(Problem('warn', no, 'literal assignment',
                                            f'{s!r}: XML2 only assigns function results'))
                state['vars'][target.lower()] = {'str': 's', 'num': 'i'}.get(a.kind, '?')
                return
        if not (toks and toks[0][0] == 'ident' and len(toks) >= 3 and toks[1] == ('punct', '(')):
            res.problems.append(Problem('warn', no, 'unparsed', f'{s!r} is not a call, keyword or assignment'))
            return
        try:
            args, j = _parse_args(toks, 1)
        except ValueError:
            res.problems.append(Problem('error', no, 'syntax', f'{s!r}: unterminated ('))
            return
        prefix, name = _split_prefix(toks[0][1])
        trailing = ''.join(t[1] for t in toks[j:])
        if trailing and trailing != ':':
            res.problems.append(Problem('warn', no, 'trailing text', f'{s!r}: text after ")": {trailing!r}'))
        if name.lower() == 'main' and not args:
            return                                   # main() calls are skipped by the engine (0x4d9cf2)
        call = Call(name, args, no, trailing, prefix, s)
        res.calls.append(call)
        ret = self._check_call(res, call, state['vars'], x1_output)
        if target is not None:
            state['vars'][target.lower()] = ret if ret in ('i', 'f', 's') else '?'
        if name in POPUP_CALLS:
            state['popup'] = no
        elif name == 'waittimed':
            state['popup'] = None                    # runs out only once the popup is closed
        elif name in POPUP_BLOCKERS and state.get('popup') and x1_output:
            res.problems.append(Problem('error', no, 'popup pending',
                                        f'{name} after the popup of line {state["popup"]} with no waittimed between: '
                                        f'the popup stays up under the menu / across the reload (in game it broke '
                                        f'the team menu); a waittimed after the popup waits for its close', name))
        if name in WAITS:
            state['console_run'] = 0
        elif name in CONSOLE_SENDERS:
            state['console_run'] += 1
            if state['console_run'] == 3:
                res.problems.append(Problem('warn', no, 'console queue',
                                            f'3rd console command ({name}) without a wait; the queue drops '
                                            f'commands when 2 are pending (0x55c426)', name))

    def check_file_bytes(self, data: bytes, *, x1_output=True) -> ScriptResult:
        """A whole script file as the engine sees it (split on CRLF)."""
        res = ScriptResult()
        text = data.decode('latin-1')
        if text.startswith('\xef\xbb\xbf'):
            res.problems.append(Problem('error', 1, 'bom', 'UTF-8 BOM: the first statement is mis-parsed'))
            text = text[3:]
        body = text.replace('\r\n', '')
        if '\n' in body or '\r' in body:
            nlf, ncr = body.count('\n'), body.count('\r')
            res.problems.append(Problem('error', 0, 'line endings',
                                        f'{nlf} bare LF / {ncr} bare CR: XMen2.exe splits on CRLF only (0x4a1290)'))
        state = {'depth': 0, 'vars': {}, 'console_run': 0}
        for no, line in enumerate(text.split('\r\n'), 1):
            self._statement(res, no, line, state, x1_output)
        if state['depth'] > 0:
            res.problems.append(Problem('error', 0, 'if/endif', f'{state["depth"]} if block(s) never closed'))
        return res

    def check_inline(self, code: str, *, x1_output=True, limit=INLINE_MAX) -> ScriptResult:
        """Inline data code (attribute value containing '('): <= 255 bytes, split on the literal \\n\\r."""
        res = ScriptResult()
        n = len(code.encode('latin-1', 'replace'))
        if n > limit:
            res.problems.append(Problem('error', 0, 'inline length',
                                        f'{n} bytes > {limit} (0x4a12b5 truncates; the tail is lost)'))
        if '\n' in code or '\r' in code:
            res.problems.append(Problem('warn', 0, 'inline separator',
                                        'real CR/LF characters; the engine splits only on the literal \\n\\r'))
        low = code.replace(INLINE_SEP, '')
        if '\\r\\n' in low or '\\n' in low:
            res.problems.append(Problem('warn', 0, 'inline separator',
                                        'escaped newline other than the literal \\n\\r the engine splits on'))
        state = {'depth': 0, 'vars': {}, 'console_run': 0}
        for no, piece in enumerate(code.split(INLINE_SEP), 1):
            self._statement(res, no, piece, state, x1_output)
        if state['depth'] > 0:
            res.problems.append(Problem('error', 0, 'if/endif', 'inline if never closed'))
        return res

    def check_console_code(self, code: str, *, prefix='runscript ', x1_output=True) -> ScriptResult:
        """Code run through the console ('runscript <code>'): no whitespace or ';', <= 127 characters total;
        if it contains '(' it must also be a valid statement."""
        res = ScriptResult()
        cmd = prefix + code
        if len(cmd) > CONSOLE_MAX:
            res.problems.append(Problem('error', 0, 'console length',
                                        f'{cmd[:60]!r}...: {len(cmd)} chars > {CONSOLE_MAX} (0x55c42f)'))
        if re.search(r'[\x00-\x20;]', code):
            res.problems.append(Problem('error', 0, 'console token',
                                        f'{code!r} contains whitespace or ";" (tokenizer 0x55b670 splits there)'))
        if '(' in code:
            sub = self.check_inline(code, x1_output=x1_output)
            res.statements += sub.statements
            res.calls += sub.calls
            res.problems += [p for p in sub.problems if p.kind != 'inline length']
        return res
