"""G3 corpus verdicts: a synthetic capacity experiment is a refusal control, never a load pass."""
import copy
import importlib
import importlib.util


def gate():
    assert importlib.util.find_spec('check_saved_zone_corpus'), 'G3 needs a provenance-aware corpus gate'
    return importlib.import_module('check_saved_zone_corpus')


def negative():
    error = 'item: id 0x20000e2 is not in this build (parked / unknown)'
    return dict(id='d1e97a5e373e', kind='lc-campaign', dump=True, w2_load=False,
                w2_load_error=error, failures=['w2 load: ' + error])


def test_saved_zone_corpus_counts_loads_and_expected_refusals_separately():
    g = gate()
    rows = [('ordinary', '0' * 40, dict(id='ordinary', dump=True, w2_load=True, failures=[])),
            ('d1e97a5e373e', 'd1e97a5e373e0cb1064d40ba46743af1db0070bb', negative())]
    result = g.classify(rows, 1)
    assert result['passed'] == 2 and result['total'] == 2
    assert result['loaded'] == 1 and result['expected_refusals'] == 1
    assert result['unexpected'] == []


def test_saved_zone_corpus_never_waives_a_different_save_or_failure():
    g = gate()
    original = negative()
    cases = []
    cases.append(('0' * 40, original))
    for field, value in [('w2_load', True), ('dump', False), ('kind', 'lc-profile'),
                         ('id', 'other'), ('w2_load_error', 'native pool overflow'),
                         ('failures', original['failures'] + ['W2 save: overflow']),
                         ('failures', []), ('failures', ['W2 load: truncated'])]:
        row = copy.deepcopy(original)
        row[field] = value
        cases.append((g.SYNTHETIC_SHA1, row))
    for digest, row in cases:
        assert g.classify([('d1e97a5e373e', digest, row)], 1)['unexpected'], row


def test_saved_zone_corpus_requires_complete_success_and_correct_host_exit():
    g = gate()
    good = dict(id='ordinary', dump=True, w2_load=True, failures=[])
    for row in (dict(good, failures=['overflow']), dict(good, w2_load=False),
                dict(good, dump=False), dict(good, id='stale'), {}):
        assert g.classify([('ordinary', '0' * 40, row)], 1)['unexpected']
    assert g.classify([('ordinary', '0' * 40, good)], 1)['unexpected']
    assert g.classify([('d1e97a5e373e', g.SYNTHETIC_SHA1, negative())], 0)['unexpected']
    assert g.classify([], 0)['unexpected']


def test_saved_zone_corpus_uses_the_host_import_verdict_for_legacy_settings():
    g = gate()
    # settings.dat is not a slot: the host dumps its successful import instead.
    settings = dict(id='settings', kind='retail-settings', size=684, dump=False,
                    import_error='', w2_load=True, w2_save=True, w2_idempotent=True, failures=[])
    settings['import'] = True
    assert g.classify([('settings', '0' * 40, settings)], 0)['loaded'] == 1
    for field in ('import', 'w2_save', 'w2_idempotent'):
        assert g.classify([('settings', '0' * 40, dict(settings, **{field: False}))], 0)['unexpected']
    assert g.classify([('settings', '0' * 40, dict(settings, kind='lc-campaign'))], 0)['unexpected']
