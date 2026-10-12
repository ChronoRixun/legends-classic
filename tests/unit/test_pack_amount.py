from xml1build import fix_ini


def test_port_owns_and_requests_xml1_pack_amount():
    assert 'PackAmount' in fix_ini.PORT_OWNED['Game']
    assert fix_ini.PACK_AMOUNT == 'xml1'
    assert fix_ini.game_keys()['PackAmount'] == 'xml1'


def test_stock_opening_does_not_request_pack_amount():
    assert 'PackAmount' not in fix_ini.game_keys(xml1_opening=False)


def test_pack_amount_is_dropped_on_stock_ini_merge():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'settings.ini'
        path.write_text('[Game]\nPackAmount=xml2\nKeepMe=example\n')
        port = {'Game': fix_ini.game_keys()}
        fix_ini.merge_ini(path, port, fix_ini.dropped_keys(port))
        assert fix_ini.read_ini(path)['Game']['PackAmount'] == 'xml1'
        stock = {'Game': fix_ini.game_keys(xml1_opening=False)}
        fix_ini.merge_ini(path, stock, fix_ini.dropped_keys(stock))
        parsed = fix_ini.read_ini(path)['Game']
        assert 'PackAmount' not in parsed
        assert parsed['KeepMe'] == 'example'
