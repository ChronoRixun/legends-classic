"""Synthetic Xtraction services regressions (issues #63 / #95); no game data."""
from xml1build.prepare import scripts as P3
from types import SimpleNamespace


def _args(text):
    return P3.parse_line(1, text).call.args


def test_menu_passes_the_point_services_and_keeps_the_native_fallback():
    lines = P3.xtraction_menu_lines('"invented_beacon"', 14, '"')
    assert lines[0] == 'x1_svc = iadd(0, 14 )'
    assert '     extractionPointServices("invented_beacon", x1_svc )' in lines
    assert '     extractionPoint("invented_beacon" )' in lines
    assert 'x1_services = xml2fixFeature("xtractionservices" )' in lines
    assert not any('getGameFlag' in line for line in lines)                 # no ftalk signal any more
    from xml1build import scripts_transform as T
    collapsed = T.xtraction_menu_fallback(lines)
    assert 'extractionPoint("invented_beacon" )' in collapsed
    assert not any('extractionPointServices' in line or 'xml2fixFeature' in line for line in collapsed)
    assert not any(line.strip() in ('else', 'endif') for line in collapsed)
    assert not T.xml2fix_guard_problems(lines)


def test_point_services_follow_the_first_games_flags():
    forge = P3.SVC_FORGE | P3.SVC_FORGE_CAMPAIGN
    full = P3.point_services('extractionPoint', _args('extractionPoint("invented_beacon")'))
    assert full == P3.SVC_LOAD | P3.SVC_DANGER_ROOM | P3.SVC_HEALER | forge
    for flags, bits in (
            (('false', 'true', 'true', 'true', 'false'),
             P3.SVC_NO_CHANGE_TEAM | P3.SVC_LOAD | P3.SVC_DANGER_ROOM | P3.SVC_HEALER | forge),
            (('true', 'false', 'false', 'false', 'true'), P3.SVC_LOAD),          # the 5th flag is never read
            (('TRUE', 'false', 'True', 'false', 'false'), P3.SVC_LOAD | P3.SVC_HEALER),
            (('false', 'true', 'false', 'false', 'false'), P3.SVC_NO_CHANGE_TEAM | P3.SVC_LOAD | P3.SVC_DANGER_ROOM),
            (('false', 'false', 'false', 'true', 'false'), P3.SVC_NO_CHANGE_TEAM | P3.SVC_LOAD | forge)):
        call = 'extractionPointLite("invented_beacon",' + ','.join(f'"{f}"' for f in flags) + ')'
        assert P3.point_services('extractionPointLite', _args(call)) == bits, call
    assert P3.point_services('extractionPointLite', _args('extractionPointLite("invented_beacon","true")')) == P3.SVC_LOAD


def test_rewriter_routes_full_and_lite_points():
    from collections import Counter
    rewriter = P3.Rewriter.__new__(P3.Rewriter)
    rewriter.STATS, rewriter.STORAGE = Counter(), {}
    for statement, bits in (('extractionPoint("invented_beacon")', 31),
                            ('extractionPointLite("invented_beacon","false","true","true","true","false")', 63),
                            ('extractionPointLite("invented_beacon","true","true","true","false","true")', 14)):
        lines = rewriter.rewrite_call(P3.parse_line(1, statement).call, None, (), 'invented', '"', 0)
        assert lines[0] == f'x1_svc = iadd(0, {bits} )', (statement, lines[0])


def test_validator_rejects_unrouted_point_calls():
    from xml1build.validate import Check, Validator
    validator = Validator.__new__(Validator)
    path = 'maps/inv/outpost.engb'
    validator._scan = SimpleNamespace(inline={path: [
        ('entity', 'actscript', 'extractionPoint("invented_beacon")'),
        ('entity', 'actscript', 'x1/invented_helper')]}, files={path: {'rel': path}})
    validator.ctx = SimpleNamespace(opt=lambda _: 'seat')
    validator.is_x1 = lambda _: True
    validator.data_items = lambda table: list(table.items())
    check = Check('V-TBD', 'invented routing')
    validator.xtraction_services(check)
    assert len(check.errors) == 1
    assert check.counts['xtraction_service_inline_checked'] == 2
