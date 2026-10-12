"""Synthetic menu permission and unlock regressions; no game data."""
from xml1build.prepare import scripts as P3
from types import SimpleNamespace
from collections import Counter


def test_menu_preserves_point_permission_and_unlock_storage():
    st = P3.Storage('pack', 'invented', off=6)
    enabled = P3.xtraction_menu_lines('"invented_beacon"', True, st, '"')
    disabled = P3.xtraction_menu_lines('"invented_beacon"', False, st, '"')
    assert 'x1_shop = getGameFlag("invented", 7 )' in enabled
    assert '     extractionPointServices("invented_beacon", x1_shop )' in enabled
    assert '     extractionPointServices("invented_beacon", 0 )' in disabled
    assert 'x1_services = xml2fixFeature("xtractionservices" )' in enabled
    assert not any('getGameFlag' in line for line in disabled)
    assert '     extractionPoint("invented_beacon" )' in enabled


def test_missing_unlock_storage_does_not_unlock_shop():
    lines = P3.xtraction_menu_lines('"invented_beacon"', True, None, '"')
    assert '     extractionPointServices("invented_beacon", 0 )' in lines


def test_menu_build_keeps_native_fallback_without_companion_calls():
    from xml1build import scripts_transform as T
    lines = P3.xtraction_menu_lines('"invented_beacon"', True, P3.Storage('pack', 'invented', off=6), '"')
    collapsed = T.xtraction_menu_fallback(lines)
    assert 'extractionPoint("invented_beacon" )' in collapsed
    assert not any('extractionPointServices' in line or 'xml2fixFeature' in line for line in collapsed)
    assert not any(line.strip() in ('else', 'endif') for line in collapsed)


def test_full_and_lite_points_keep_the_fourth_service_flag():
    rewriter = P3.Rewriter.__new__(P3.Rewriter)
    rewriter.STATS, rewriter.STORAGE = Counter(), {('m', 'ftalk'): P3.Storage('pack', 'invented', off=6)}
    for statement, permitted in (
        ('extractionPoint("invented_beacon")', True),
        ('extractionPointLite("invented_beacon","false","true","true","true","false")', True),
        ('extractionPointLite("invented_beacon","true","true","true","false","true")', False)):
        lines = rewriter.rewrite_call(P3.parse_line(1, statement).call, None, (), 'invented', '"', 0)
        assert any('x1_shop = getGameFlag' in line for line in lines) == permitted


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


def test_point_services_follow_the_first_games_flags():
    """Full points: Load, Danger Room and Healer (the DLL adds the campaign checks); lite: flags 2 / 3 / 4."""
    def args(text):
        return P3.parse_line(1, text).call.args
    full = P3.point_services('extractionPoint', args('extractionPoint("invented_beacon")'))
    assert full == (True, P3.SVC_LOAD | P3.SVC_DANGER_ROOM | P3.SVC_HEALER)
    for flags, forge, bits in (
            (('false', 'true', 'true', 'true', 'false'), True, P3.SVC_LOAD | P3.SVC_DANGER_ROOM | P3.SVC_HEALER),
            (('true', 'false', 'false', 'false', 'true'), False, P3.SVC_LOAD),       # the 5th flag is never read
            (('TRUE', 'false', 'True', 'false', 'false'), False, P3.SVC_LOAD | P3.SVC_HEALER),
            (('false', 'true', 'false', 'false', 'false'), False, P3.SVC_LOAD | P3.SVC_DANGER_ROOM)):
        call = 'extractionPointLite("invented_beacon",' + ','.join(f'"{f}"' for f in flags) + ')'
        assert P3.point_services('extractionPointLite', args(call)) == (forge, bits), call
    short = P3.point_services('extractionPointLite', args('extractionPointLite("invented_beacon","true")'))
    assert short == (False, P3.SVC_LOAD)


def test_services_bits_are_added_to_the_forge_permission():
    st = P3.Storage('pack', 'invented', off=6)
    lines = P3.xtraction_menu_lines('"invented_beacon"', True, st, '"', 14)
    assert 'x1_svc = iadd(x1_shop, 14 )' in lines
    assert '     extractionPointServices("invented_beacon", x1_svc )' in lines
    lines = P3.xtraction_menu_lines('"invented_beacon"', False, st, '"', 4)
    assert 'x1_svc = iadd(0, 4 )' in lines and not any('getGameFlag' in line for line in lines)
    from xml1build import scripts_transform as T
    collapsed = T.xtraction_menu_fallback(lines)
    assert 'extractionPoint("invented_beacon" )' in collapsed
    assert not T.xml2fix_guard_problems(lines)
