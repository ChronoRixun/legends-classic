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
