"""xml1build.script_functions - validate V57 (script function names): every function the generated output calls is a
retail XMen2.exe name or an xml2-fix one, and the names the build relies on fit the script function limit the build's
xml2-fix.ini asks for.

Engine facts (xml2-fix docs/script-functions.md): XMen2.exe resolves a script's function names when the script
compiles (0x4d8970 -> 0x4d6910), exact case, through a tree of 320 names; a name it doesn't know drops that statement
without a word. Its own 308 names (research/scripts/xml2_api.json: 289 + 19 builtins) and xml2-fix's functions
(research/scripts/xml2fix_api.json; the fix registers all of them with [Game] ForcedTeams) share that tree, and a
registration past the 320th is skipped silently unless [Limits] ScriptFunctions raises it. V7 models the parser and
already reports most unknown names; this check is the cheap, strict membership rule over XML1 output (no XML2 base
content) with V7's two allowances only (KNOWN_DEAD_SCRIPT_FINDINGS, inherited drops default.xbe made too), plus the
count against the limit.

Pure helpers + validate(v, ck); no file writes."""
from __future__ import annotations

STOCK_LIMIT = 320          # XMen2.exe's tree (0x4d7637)
MAX_LIMIT = 4096           # xml2-fix's ceiling


def registered_names(retail_api, fix_api) -> set:
    """every name the game's tree must hold in a port build: XMen2.exe's (builtins included) and every xml2-fix
    function (the fix registers all of them, whatever the build calls)."""
    return set(retail_api) | set(fix_api)


def limit_problems(count: int, limits: dict) -> list:
    """[message]: the `count` names against [Limits] ScriptFunctions in `limits` (fix_ini.LIMITS)."""
    raw = limits.get('ScriptFunctions')
    if raw is None:
        if count > STOCK_LIMIT:
            return [f"{count} script function names but no [Limits] ScriptFunctions: the fix raises the game's "
                    f"{STOCK_LIMIT} by default only with [Game] ForcedTeams - write the key"]
        return []
    try:
        limit = int(str(raw).strip())
    except ValueError:
        return [f'[Limits] ScriptFunctions={raw!r} is not a number']
    if not STOCK_LIMIT <= limit <= MAX_LIMIT:
        return [f'[Limits] ScriptFunctions={limit} is outside {STOCK_LIMIT}..{MAX_LIMIT} (xml2-fix ignores it)']
    if count > limit:
        return [f'{count} script function names but [Limits] ScriptFunctions={limit}: the game drops the last '
                f'{count - limit} and every script line calling them']
    return []


def unknown_calls(calls, api, allowed=lambda call: False) -> list:
    """the calls whose function (exact case) is not in `api`, minus those `allowed(call)` accepts."""
    return [c for c in calls if c.name not in api and not allowed(c)]


def validate(v, ck):
    """V57 script function names, over the validate.Validator `v`."""
    from . import common as C
    from . import fix_ini as FI
    from . import validate as V
    from . import validate_script as VS
    retail = v.ctx.research_json('scripts/xml2_api.json')
    fix = v.ctx.research_json(C.XML2FIX_API_JSON)['functions']
    names = registered_names(retail, fix)
    ck.set('script_function_names', len(names))
    for msg in limit_problems(len(names), FI.LIMITS):
        ck.error(msg)
    api = v.ctx.xml2_api

    def allowance(ref, verbatim):
        def ok(call):
            if ref is not None and (ref, 'unknown function', call.name) in V.KNOWN_DEAD_SCRIPT_FINDINGS:
                return True
            p = VS.Problem('error', call.line, 'unknown function', '', call.name, call)
            return v.inherited_drop(p, verbatim)
        return ok

    checked = 0
    for r in sorted(v.script_set()):
        if not v.is_x1(r):
            continue
        res = v.script(r)
        if res is None:
            continue
        checked += 1
        ref = C.script_ref(r)

        def verbatim(p, ref=ref):
            return p.call is not None and v._stmt_key(p.call.text) in v.x1_script_statements(ref)
        for c in unknown_calls(res.calls, api, allowance(ref, verbatim)):
            ck.error(f'{v.idx.get(r) or r}:{c.line}: {c.name}() is neither an XMen2.exe nor an xml2-fix script '
                     f'function (the game drops the line)')
    ck.set('script_function_scripts_checked', checked)
    code_checked = 0
    for table in (v.scan.inline, v.scan.runscripts):
        for n, lst in v.data_items(table):
            if not v.is_x1(n):
                continue
            for item in lst:
                code = item[2] if isinstance(item, tuple) else item
                if not code:
                    continue
                code_checked += 1
                in_src = code in v.x1_source_values(n)
                res = v.checker.check_inline(code, x1_output=True)
                for c in unknown_calls(res.calls, api, allowance(None, lambda _p, s=in_src: s)):
                    ck.error(f'{v.scan.files[n]["rel"]}: inline code {code[:80]!r}: {c.name}() is neither an '
                             f'XMen2.exe nor an xml2-fix script function (the game drops the statement)')
    ck.set('script_function_data_code_checked', code_checked)
