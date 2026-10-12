from xml1build import fix_ini

def test_port_owns_and_enables_rule():
    assert 'ExplosiveFirstHit' in fix_ini.PORT_OWNED['Game']
    assert fix_ini.game_keys()['ExplosiveFirstHit'] == '1'

def test_stock_opening_does_not_request_rule():
    assert 'ExplosiveFirstHit' not in fix_ini.game_keys(xml1_opening=False)


def test_rule_is_removed_on_stock_ini_merge():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'settings.ini'
        path.write_text('[Game]\nExplosiveFirstHit=0\nKeepMe=example\n')
        port = {'Game': fix_ini.game_keys()}
        fix_ini.merge_ini(path, port, fix_ini.dropped_keys(port))
        assert fix_ini.read_ini(path)['Game']['ExplosiveFirstHit'] == '1'
        stock = {'Game': fix_ini.game_keys(xml1_opening=False)}
        fix_ini.merge_ini(path, stock, fix_ini.dropped_keys(stock))
        parsed = fix_ini.read_ini(path)['Game']
        assert 'ExplosiveFirstHit' not in parsed
        assert parsed['KeepMe'] == 'example'
