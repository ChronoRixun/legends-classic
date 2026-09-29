"""Parser for Raven "BehavEd" script files (.py) used by X-Men Legends 1/2.

The engine (XMen2.exe 0x4da450 / 0x4d9740) splits the file on "\\r\\n" and parses each line on its
own: keywords if / elif / elseif / else / endif / def, '#' comments, "quoted" or 'quoted' strings,
'(' ')' calls, '=' assignment, a 'game.' prefix is discarded.  This module mirrors that with a
tolerant tokenizer so both corpora can be analysed and rewritten.

parse_file(bytes) -> Script(lines=[Line...], eol='crlf'|'lf'|'mixed', ...)
Line fields: no, raw, indent, kind, and for kind:
   'blank' | 'comment' (text)
   'if'/'elif'/'else'/'endif' (cond = (lhs, op, rhs) or raw text)
   'call'   (call=Call)
   'assign' (target, value = Call | Arg)
   'def'/'import'/'other' (text)
Call: name, prefix ('game.' or ''), args [Arg], trailing (text after ')')
Arg: kind in {'str','num','ident','call','expr'}, text (source text), value (python value), quote
"""
import re

KEYWORDS = {'if', 'elif', 'elseif', 'else', 'endif', 'def', 'import', 'while', 'endwhile', 'for',
            'return', 'pass', 'from', 'print'}

TOKEN_RE = re.compile(r'''
    (?P<ws>[ \t]+)
  | (?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<num>-?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)
  | (?P<op>==|!=|<=|>=|<|>|=|%|\+|-|\*|/)
  | (?P<punct>[(),:\[\]])
  | (?P<comment>\#.*)
  | (?P<bad>.)
''', re.X)


class Arg:
    __slots__ = ('kind', 'text', 'value', 'quote')

    def __init__(self, kind, text, value=None, quote=None):
        self.kind, self.text, self.value, self.quote = kind, text, value, quote

    def __repr__(self):
        return f'Arg({self.kind},{self.text!r})'


class Call:
    __slots__ = ('name', 'prefix', 'args', 'trailing', 'space_before_paren')

    def __init__(self, name, prefix, args, trailing='', space_before_paren=''):
        self.name, self.prefix, self.args, self.trailing = name, prefix, args, trailing
        self.space_before_paren = space_before_paren

    def __repr__(self):
        return f'Call({self.prefix}{self.name}{self.args})'


class Line:
    def __init__(self, no, raw):
        self.no, self.raw = no, raw
        self.indent = raw[:len(raw) - len(raw.lstrip(' \t'))]
        self.kind = None
        self.call = None
        self.target = None
        self.value = None
        self.cond = None
        self.text = raw.strip()
        self.error = None
        self.trailing_comment = None

    def __repr__(self):
        return f'<{self.no}:{self.kind} {self.text!r}>'


def tokenize(s):
    toks = []
    for m in TOKEN_RE.finditer(s):
        k = m.lastgroup
        if k == 'ws':
            toks.append(('ws', m.group()))
            continue
        toks.append((k, m.group()))
    return toks


def _strip_ws(toks):
    return [t for t in toks if t[0] != 'ws']


def _str_value(tok):
    q = tok[0]
    body = tok[1:-1]
    return body, q


def parse_args(toks, i):
    """toks without ws, toks[i] is '('. returns (args, index after ')') or raises ValueError"""
    assert toks[i] == ('punct', '(')
    i += 1
    args = []
    cur = []
    depth = 0
    while i < len(toks):
        t = toks[i]
        if t == ('punct', '(') :
            depth += 1
        elif t == ('punct', ')'):
            if depth == 0:
                if cur or args:
                    args.append(make_arg(cur))
                return args, i + 1
            depth -= 1
        elif t == ('punct', ',') and depth == 0:
            args.append(make_arg(cur))
            cur = []
            i += 1
            continue
        cur.append(t)
        i += 1
    raise ValueError('unterminated (')


def make_arg(toks):
    text = ''.join(t[1] for t in toks)
    if len(toks) == 1:
        k, v = toks[0]
        if k == 'str':
            body, q = _str_value(v)
            return Arg('str', v, body, q)
        if k == 'num':
            return Arg('num', v, float(v) if ('.' in v or 'e' in v.lower()) else int(v))
        if k == 'ident':
            return Arg('ident', v, v)
    if len(toks) == 2 and toks[0] == ('op', '-') and toks[1][0] == 'num':
        v = '-' + toks[1][1]
        return Arg('num', v, float(v) if '.' in v else int(v))
    if len(toks) == 0:
        return Arg('empty', '')
    if toks[0][0] == 'ident' and len(toks) >= 3 and toks[1] == ('punct', '('):
        try:
            args, j = parse_args(toks, 1)
            if j == len(toks):
                pfx, name = split_prefix(toks[0][1])
                return Arg('call', text, Call(name, pfx, args))
        except ValueError:
            pass
    return Arg('expr', text)


def split_prefix(ident):
    if '.' in ident:
        pfx, name = ident.rsplit('.', 1)
        return pfx + '.', name
    return '', ident


def parse_line(no, raw):
    ln = Line(no, raw)
    s = raw.strip(' \t')
    if not s:
        ln.kind = 'blank'
        return ln
    if s.startswith('#'):
        ln.kind = 'comment'
        return ln
    toks_ws = tokenize(s)
    toks = _strip_ws(toks_ws)
    if toks and toks[-1][0] == 'comment':
        ln.trailing_comment = toks[-1][1]
        toks = toks[:-1]
    if not toks:
        ln.kind = 'comment'
        return ln
    first = toks[0]
    if first[0] == 'ident' and first[1] in KEYWORDS:
        kw = first[1]
        ln.kind = 'elif' if kw in ('elif', 'elseif') else kw
        ln.kw = kw
        rest = toks[1:]
        if rest and rest[-1] == ('punct', ':'):
            ln.colon = True
            rest = rest[:-1]
        else:
            ln.colon = False
        if kw in ('if', 'elif', 'elseif', 'while'):
            ops = [k for k, t in enumerate(rest) if t[0] == 'op' and t[1] in ('==', '!=', '<', '>', '<=', '>=')]
            if len(ops) == 1:
                k = ops[0]
                ln.cond = (make_arg(rest[:k]), rest[k][1], make_arg(rest[k + 1:]))
            else:
                ln.cond = ('raw', ''.join(t[1] for t in rest))
        ln.rest = rest
        return ln
    # assignment
    if first[0] == 'ident' and len(toks) >= 3 and toks[1] == ('op', '='):
        ln.kind = 'assign'
        ln.target = first[1]
        ln.value = make_arg(toks[2:])
        return ln
    # call statement
    if first[0] == 'ident' and len(toks) >= 3 and toks[1] == ('punct', '('):
        try:
            args, j = parse_args(toks, 1)
        except ValueError as e:
            ln.kind = 'other'
            ln.error = str(e)
            return ln
        pfx, name = split_prefix(first[1])
        trailing = ''.join(t[1] for t in toks[j:])
        # remember whether BehavEd put a space before '('
        m = re.match(r'[A-Za-z_][A-Za-z0-9_.]*([ \t]*)\(', s)
        ln.kind = 'call'
        ln.call = Call(name, pfx, args, trailing, m.group(1) if m else '')
        return ln
    ln.kind = 'other'
    return ln


class Script:
    def __init__(self, data):
        self.data = data
        n_crlf = data.count(b'\r\n')
        n_lf = data.count(b'\n') - n_crlf
        self.eol = 'crlf' if n_lf == 0 and n_crlf else ('lf' if n_crlf == 0 and n_lf else ('mixed' if n_lf else 'none'))
        self.bom = data.startswith(b'\xef\xbb\xbf')
        text = data.decode('latin-1')
        if self.bom:
            text = text[3:]
        self.final_newline = text.endswith('\n')
        # the engine splits on CRLF; for analysis we split on any newline
        raw_lines = re.split(r'\r\n|\n|\r', text)
        if raw_lines and raw_lines[-1] == '':
            raw_lines = raw_lines[:-1]
        self.lines = [parse_line(i + 1, l) for i, l in enumerate(raw_lines)]
        self.tabs = any('\t' in l.indent for l in self.lines)
        self.nonascii = any(b > 127 for b in data)

    def calls(self):
        """yield (line, Call, context) for statement calls and assignment/if-embedded calls"""
        for ln in self.lines:
            if ln.kind == 'call':
                yield ln, ln.call, 'stmt'
                for a in ln.call.args:
                    if a.kind == 'call':
                        yield ln, a.value, 'nested'
            elif ln.kind == 'assign' and ln.value.kind == 'call':
                yield ln, ln.value.value, 'assign'
                for a in ln.value.value.args:
                    if a.kind == 'call':
                        yield ln, a.value, 'nested'


def parse_file(path_or_bytes):
    data = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, 'rb').read()
    return Script(bytes(data))
