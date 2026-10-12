"""Synthetic checks for validate V-TBD (script function names, script_functions.py): every function XML1 output calls
is an XMen2.exe or xml2-fix name, and the names a port build relies on fit xml2-fix's [Limits] ScriptFunctions.
Invented function names and scripts only; no game data is read."""
from types import SimpleNamespace

from xml1build import fix_ini as FI
from xml1build import script_functions as SFN
from xml1build import validate as V
from xml1build import validate_script as VS

RETAIL = {f'retailFn{i:03d}': {'args': 'i', 'ret': 'n'} for i in range(300)}
RETAIL.update({'iadd': {'args': 'ii', 'ret': 'i'}, 'waittimed': {'args': 'f', 'ret': 'w'}})
FIX = {'inventedFixFn': {'args': 's', 'ret': 'i'}, 'otherFixFn': {'args': 'ai', 'ret': 'n'}}


def test_the_port_writes_the_raised_limit_explicitly():
    assert FI.LIMITS['ScriptFunctions'] == '1024' and 'ScriptFunctions' in FI.PORT_OWNED['Limits']
    assert SFN.limit_problems(320 + 64, FI.LIMITS) == []


def test_registered_names_are_retail_and_every_fix_function():
    names = SFN.registered_names(RETAIL, FIX)
    assert len(names) == 304 and 'inventedFixFn' in names and 'iadd' in names
    assert len(SFN.registered_names(RETAIL, {'iadd': {}})) == 302          # a name in both counts once


def test_limit_problems_against_the_ini():
    assert SFN.limit_problems(320, {}) == []                                 # the game's own tree holds 320
    missing = SFN.limit_problems(321, {})
    assert len(missing) == 1 and 'no [Limits] ScriptFunctions' in missing[0]
    assert SFN.limit_problems(1024, {'ScriptFunctions': '1024'}) == []
    over = SFN.limit_problems(1030, {'ScriptFunctions': '1024'})
    assert len(over) == 1 and 'drops the last 6' in over[0]
    assert SFN.limit_problems(300, {'ScriptFunctions': '300'})               # below the game's own: ignored by the fix
    assert SFN.limit_problems(300, {'ScriptFunctions': '5000'})              # above the fix's ceiling
    assert SFN.limit_problems(300, {'ScriptFunctions': 'lots'})


def test_unknown_calls_are_exact_case_with_allowances():
    calls = [VS.Call('retailFn001', [], 1), VS.Call('RetailFn001', [], 2), VS.Call('inventedFixFn', [], 3),
             VS.Call('notAFunction', [], 4)]
    api = dict(RETAIL, **FIX)
    assert [c.line for c in SFN.unknown_calls(calls, api)] == [2, 4]       # a mis-cased name is unknown too
    assert [c.line for c in SFN.unknown_calls(calls, api, lambda c: c.name == 'notAFunction')] == [2]


def _validator(scripts, inline=None, x1_original=None, retail=RETAIL, fix=FIX, seat=True):
    """a stand-in for validate.Validator with the members V-TBD uses: scripts = {rel: (is_x1, text)}."""
    api = dict(retail, **(fix if seat else {}))
    checker = VS.ScriptChecker(api)
    x1checker = VS.ScriptChecker({'retailFn001': {'args': 'i', 'ret': 'n'}})   # "XML1's own table"
    research = {'scripts/xml2_api.json': retail, 'scripts/xml2fix_api.json': {'functions': fix}}
    files = {n: {'rel': n} for n in (inline or {})}
    v = SimpleNamespace(
        ctx=SimpleNamespace(research_json=lambda rel: research[rel], xml2_api=api),
        checker=checker, x1checker=x1checker,
        scan=SimpleNamespace(inline=dict(inline or {}), runscripts={}, files=files),
        idx=SimpleNamespace(get=lambda n: n),
        script_set=lambda: set(scripts),
        is_x1=lambda n: scripts[n][0] if n in scripts else True,
        script=lambda n: checker.check_file_bytes(scripts[n][1].encode('latin-1'), x1_output=scripts[n][0]),
        data_items=lambda table: sorted(table.items()),
        x1_source_values=lambda n: set(),
        x1_script_statements=lambda ref: set((x1_original or {}).get(ref, ())),
        _stmt_key=V.Validator._stmt_key)
    v.inherited_drop = lambda p, verbatim: V.Validator.inherited_drop(v, p, verbatim)
    ck = V.Check('V-TBD', 'script function names')
    SFN.validate(v, ck)
    return ck


def test_v_tbd_accepts_retail_and_fix_names_and_ignores_xml2_base_content():
    ck = _validator({'scripts/inv/zone1.py': (True, 'retailFn001(1 )\r\nx = inventedFixFn("a" )\r\n'),
                     'scripts/base/xml2_own.py': (False, 'xml2OnlyMissingFn(1 )\r\n')},
                    inline={'maps/inv/zone1.engb': [('entity', 'actscript', "otherFixFn('_OWNER_', 2 )")]})
    assert not ck.errors, ck.errors
    assert ck.counts['script_function_names'] == 304
    assert ck.counts['script_function_scripts_checked'] == 1 and ck.counts['script_function_data_code_checked'] == 1


def test_v_tbd_rejects_unknown_and_miscased_calls_in_xml1_output():
    ck = _validator({'scripts/inv/zone1.py': (True, 'retailFn001(1 )\r\ninventedTypo(1 )\r\nINVENTEDFIXFN("a" )\r\n')},
                    inline={'maps/inv/zone1.engb': [('entity', 'actscript', "missingDataFn('_OWNER_' )")]})
    assert len(ck.errors) == 3, ck.errors
    assert 'zone1.py:2: inventedTypo()' in ck.errors[0] and 'zone1.py:3: INVENTEDFIXFN()' in ck.errors[1]
    assert 'missingDataFn()' in ck.errors[2]


def test_v_tbd_fix_names_need_a_seat_build():
    ck = _validator({'scripts/inv/zone1.py': (True, 'x = inventedFixFn("a" )\r\n')}, seat=False)
    assert len(ck.errors) == 1 and 'inventedFixFn()' in ck.errors[0]


def test_v_tbd_keeps_v7s_allowances():
    dead_ref, _, dead_fn = sorted(f for f in V.KNOWN_DEAD_SCRIPT_FINDINGS if f[1] == 'unknown function')[0]
    ck = _validator({f'scripts/{dead_ref}.py': (True, f'{dead_fn}( )\r\n'),
                     'scripts/inv/zone2.py': (True, 'inheritedDropFn(1 )\r\ngeneratedDropFn(1 )\r\n')},
                    x1_original={'inv/zone2': ['inheritedDropFn(1)']})
    # the dead developer line and the verbatim XML1 line (XML1's own table lacks it too) are allowed; a generated one isn't
    assert len(ck.errors) == 1 and 'generatedDropFn()' in ck.errors[0], ck.errors


def test_v_tbd_count_over_the_limit_is_an_error():
    retail = {f'retailFn{i:03d}': {'args': '', 'ret': 'n'} for i in range(1020)}
    ck = _validator({}, retail=retail)
    assert ck.counts['script_function_names'] == 1022 and ck.errors == []
    retail = {f'retailFn{i:04d}': {'args': '', 'ret': 'n'} for i in range(1030)}
    ck = _validator({}, retail=retail)
    assert len(ck.errors) == 1 and 'ScriptFunctions=1024' in ck.errors[0]
