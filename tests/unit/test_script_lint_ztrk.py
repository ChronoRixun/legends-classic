"""Pure helpers with no other unit coverage, on made-up inputs: xml1build.scripts_lint (the offline mirror of the
engine's per-line script checks, the console-queue and roster rules) and xml1build.lib.ztrk (the ZTRK track
bytecode reader). Function names and API tables here are invented, apart from the engine names the rules key on."""

from xml1build import scripts_lint as L
from xml1build.lib import ztrk as Z

API = {'foo': {'args': 'is', 'ret': 'i'}, 'nothing': {'args': '', 'ret': None}}


# ---------------------------------------------------------------------------------------------------- scripts_lint
def test_tokenising_helpers_respect_quotes():
    assert L.strip_comment('a("#x") # y') == 'a("#x") '
    assert L.strip_comment("b('#') ") == "b('#') "
    assert L.split_args('1, "a,b", f(2, 3), ') == ['1', '"a,b"', 'f(2, 3)', '']
    assert L.split_args('') == [] and L.split_args(' x ') == ['x']
    assert L.literal_value('"abc"') == 'abc' and L.literal_value("'a'") == 'a'
    assert L.literal_value('"a\'') is None and L.literal_value('"') is None
    assert L.compact(' a ( "b c" , 1 ) ') == 'a("b c",1)'


def test_argkind_classifies_literals_variables_and_calls():
    vars_ = {'v': 'i'}
    assert [L.argkind(a, vars_) for a in ('"s"', '-1.5', '2e3', 'V', '_owner_', 'nope', 'f(1)', '1+')] == \
        ['s', 'n', 'n', 'v:i', 'ent', 'undef', 'call', 'other']


def test_check_call_finds_case_arity_type_and_forbidden_problems():
    assert L.check_call('foo', ['1', '"a"'], {}, API) == ('i', [])
    assert L.check_call('game.foo', ['1', '"a"'], {}, API) == ('i', [])
    assert L.check_call('Foo', ['1', '"a"'], {}, API) == (None, ['wrong case: Foo (registered as foo)'])
    assert L.check_call('bar', [], {}, API) == (None, ['unregistered function bar'])
    ret, probs = L.check_call('foo', ['1'], {}, API)
    assert ret == 'i' and len(probs) == 1 and 'argc 1 != 2' in probs[0]
    _, probs = L.check_call('foo', ['"a"', '2'], {}, API)
    assert probs == ['foo: string for i parameter: "a"', 'foo: number for s parameter: 2']
    _, probs = L.check_call('foo', ['g(1)', '"a"'], {}, API)
    assert probs == ['foo: nested call argument g(1)']
    assert L.check_call('loadMap', ['"z"'], {}, API)[1] == ['XML1-only / no-op call loadMap left in converted code']
    assert L.check_call('loadMap', ['"z"'], {}, API, forbidden=False)[1] == ['unregistered function loadMap']


def test_lint_lines_tracks_variables_blocks_and_skipped_lines():
    lines = ['x = foo(1, "a")      # x becomes an int', 'if x == 1:', '  nothing()', 'elif x > y:', 'endif',
             'endif', 'def main():', 'main()', 'if __name__ == "__main__":', 'y = 3', 'what is this']
    problems, info = L.lint_lines(lines, API)
    assert problems == [(4, 'condition', "operand 'y' is undef"), (6, 'block', 'endif without if'),
                        (9, 'condition', "operand '__name__' is undef"),
                        (10, 'assign', "assignment of a non-call: 'y = 3'"), (11, 'unparsed', 'what is this'),
                        (0, 'block', 'if/endif imbalance +1')]
    assert info['statements'] == 11 and [c[1] for c in info['calls']] == ['foo', 'nothing']
    problems, _ = L.lint_lines(['x = foo(1, "a")', 'foo(x, x)'], API)
    assert problems == [(2, 'call', 'foo: number for s parameter: x')]


def test_lint_script_bytes_flags_bare_line_ends_and_nul():
    problems, info = L.lint_script_bytes(b'nothing()\r\nnothing()\r\n', API)
    assert problems == [] and info['statements'] == 2
    # the engine splits on CRLF only: a bare LF glues two statements into one line it cannot parse
    problems, _ = L.lint_script_bytes(b'nothing()\nnothing()\x00\r\n', API)
    assert [p[:2] for p in problems] == [(0, 'bytes'), (0, 'eol'), (1, 'unparsed')]


def test_inline_and_console_limits():
    code = L.INLINE_SEP.join(['foo(1, "a")', 'nothing()'])
    assert L.split_inline(code) == ['foo(1, "a")', 'nothing()']
    assert L.lint_inline(code, API)[0] == []
    long = L.INLINE_SEP.join(['nothing()'] * 30)
    assert L.lint_inline(long, API)[0][0][1] == 'size'
    assert L.console_problems('x') == []
    assert len(L.console_problems('a;b')) == 1
    fits = 'x' * (L.CONSOLE_MAX - len(L.RUNSCRIPT))
    assert L.console_problems(fits) == [] and len(L.console_problems(fits + 'x')) == 1


def test_console_overflows_is_branch_aware():
    # exclusive branches are not added together, a wait resets the count
    lines = ['openmenu(1)', 'if a == 1:', 'closemenu()', 'else', 'closemenu()', 'endif', 'waittimed(1)',
             'openmenu(2)', 'openmenu(3)']
    assert L.console_overflows(lines) == []
    assert L.console_overflows(lines[:6] + ['game.openmenu(2)']) == [(7, 'game.openmenu', 3)]
    # an if without else may be skipped: the count after endif is the larger of both paths
    lines = ['openmenu(1)', 'if a == 1:', 'openmenu(2)', 'endif', 'x = closemenu()']
    assert L.console_overflows(lines) == [(5, 'closemenu', 3)]
    assert L.console_overflows(lines, limit=3) == []


def test_roster_problems_need_the_flag_before_the_lite_extraction():
    lines = ['extractionPointLite("_ACTIVE_HERO_", 1)', 'setGameFlag("danv", 1, 1)',
             'extractionPointLite("_ACTIVE_HERO_", 1)', 'extractionPointLite("someone", 1)', 'game.loadMapAddTeam("z")']
    assert [(ln, kind) for ln, kind, _ in L.roster_problems(lines)] == [(1, 'roster'), (5, 'roster')]


# ---------------------------------------------------------------------------------------------------- ztrk
# event byte = type | code; code -> prefix bytes (3: a 1-byte delta), type 0x10 = controller (cmd 4 = sound index)
TRACK = b'ZTRK' + bytes([0x10, 4, 7,  0x13, 5, 4, 9,  0x10, 4, 0xFF,  0x10, 0, 100,  0x18, 0, 0]) + b'\0\0'


def test_ztrk_parse_and_sound_refs():
    ev = Z.parse(TRACK)
    assert [(off, typ) for off, b, pre, typ, args in ev] == [(4, 0x10), (7, 0x10), (11, 0x10), (14, 0x10), (17, 0x18)]
    assert ev[1][2] == b'\x05' and ev[1][4] == b'\x04\x09'
    # index 0xFF means "no sound", cmd 0 is volume: neither is a sound reference
    assert Z.sound_refs(TRACK) == [6, 10]
    assert [TRACK[o] for o in Z.sound_refs(TRACK)] == [7, 9]


def test_ztrk_remap_changes_only_sound_indexes():
    out = Z.remap(TRACK, lambda i: i + 1)
    assert len(out) == len(TRACK) and (out[6], out[10]) == (8, 10)
    assert [i for i in range(len(out)) if out[i] != TRACK[i]] == [6, 10]
    try:
        Z.remap(TRACK, lambda i: 0xFF)
    except Z.ZtrkError:
        pass
    else:
        raise AssertionError('0xFF is not encodable as a sound index')


def test_ztrk_rejects_malformed_tracks():
    for blob, why in ((b'XTRK', 'no magic'), (b'ZTRK\xf8', 'extended'), (b'ZTRK\x48', 'unknown type'),
                      (b'ZTRK\x16\x01\x02', 'truncated'), (b'ZTRK\x10\x04', 'truncated')):
        try:
            Z.parse(blob)
        except Z.ZtrkError as e:
            assert why in str(e), (blob, e)
        else:
            raise AssertionError(f'{blob!r} must not parse')
    assert Z.parse(b'ZTRK') == [] and Z.parse(b'ZTRK\0\0\0') == []
