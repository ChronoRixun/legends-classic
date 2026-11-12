"""G3 corpus verdicts: a synthetic capacity experiment is a refusal control, never a load pass."""
import contextlib
import copy
from datetime import datetime, timezone
import importlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess


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


def corpus(tmp_path, ids):
    """A disposable --list and its inputs; the native host is stubbed, not run."""
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    rows = []
    for identity in ids:
        path = inputs / (identity + '.lcsave')
        path.write_bytes(b'disposable ' + identity.encode())
        rows.append(f'{identity}\t{path}')
    listing = tmp_path / 'unique-list.txt'
    listing.write_text('\n'.join(rows) + '\n', encoding='utf-8')
    return listing


def stub_host(g, *, started=None):
    """Stand in for the native host: one successful verdict per listed input."""
    real = g.subprocess.run

    def run(command, **kwargs):
        out = Path(command[command.index('--out') + 1])
        if started is not None:
            started.append(sorted(p.name for p in out.iterdir()))
        for line in Path(command[command.index('--list') + 1]).read_text(encoding='utf-8').splitlines():
            identity = line.split('\t', 1)[0]
            (out / (identity + '.json')).write_text(
                json.dumps(dict(id=identity, dump=True, w2_load=True, failures=[])), encoding='utf-8')
        return subprocess.CompletedProcess(command, 0)

    g.subprocess.run = run
    return lambda: setattr(g.subprocess, 'run', real)


def freeze_clock(g, moment):
    """Pin the superseded timestamp so its name is deterministic."""
    real = g.datetime

    class Frozen(real):
        @classmethod
        def now(cls, tz=None):
            return moment if tz is not None else moment.replace(tzinfo=None)

    g.datetime = Frozen
    return lambda: setattr(g, 'datetime', real)


def run_gate(g, tmp_path, listing, out, extra=()):
    streams = io.StringIO()
    with contextlib.redirect_stdout(streams), contextlib.redirect_stderr(streams):
        code = g.main(['--host', str(tmp_path / 'stub-host'), '--list', str(listing),
                       '--data', str(tmp_path / 'build'), '--out', str(out),
                       '--require-count', '1', *extra])
    return code, streams.getvalue()


def test_saved_zone_corpus_refuses_an_existing_out_and_moves_nothing(tmp_path):
    g = gate()
    listing = corpus(tmp_path, ['ordinary'])
    out = tmp_path / 'results'
    out.mkdir()
    (out / 'ordinary.json').write_text('stale verdict from a crashed run', encoding='utf-8')
    restore = stub_host(g)
    try:
        code, output = run_gate(g, tmp_path, listing, out)
    finally:
        restore()
    lines = [line for line in output.splitlines() if line.strip()]
    assert code != 0
    assert len(lines) == 1 and '--replace-existing' in lines[0], lines
    assert (out / 'ordinary.json').read_text(encoding='utf-8') == 'stale verdict from a crashed run'
    assert not (out / 'summary.json').exists()
    assert list(tmp_path.glob('results.superseded-*')) == []


def test_saved_zone_corpus_moves_an_existing_out_aside_with_the_flag(tmp_path):
    g = gate()
    listing = corpus(tmp_path, ['ordinary'])
    out = tmp_path / 'results'
    out.mkdir()
    (out / 'ordinary.json').write_text('stale verdict from a crashed run', encoding='utf-8')
    stale = (out / 'ordinary.json').read_bytes()
    started = []
    restores = [freeze_clock(g, datetime(2026, 11, 11, 16, 27, 21, tzinfo=timezone.utc)),
                stub_host(g, started=started)]
    try:
        code, output = run_gate(g, tmp_path, listing, out, ['--replace-existing'])
    finally:
        for restore in reversed(restores):
            restore()
    assert code == 0, output
    superseded = tmp_path / 'results.superseded-20261111T162721Z'
    assert sorted(p.name for p in tmp_path.glob('results.superseded-*')) == [superseded.name]
    assert (superseded / 'ordinary.json').read_bytes() == stale
    assert started == [['native.log']]          # the new --out was empty when the host started
    assert (out / 'ordinary.json').exists() and (out / 'summary.json').exists()
    assert 'moved to' in output


def test_saved_zone_corpus_suffixes_a_second_superseded_name(tmp_path):
    g = gate()
    listing = corpus(tmp_path, ['ordinary'])
    out = tmp_path / 'results'
    out.mkdir()
    (out / 'ordinary.json').write_text('newer stale verdict', encoding='utf-8')
    taken = tmp_path / 'results.superseded-20261111T162721Z'
    taken.mkdir()
    (taken / 'keep.json').write_text('older run', encoding='utf-8')
    restores = [freeze_clock(g, datetime(2026, 11, 11, 16, 27, 21, tzinfo=timezone.utc)), stub_host(g)]
    try:
        second = g.superseded_path(out)            # the base timestamp is taken, so -2 is next
        code, output = run_gate(g, tmp_path, listing, out, ['--replace-existing'])
        # the loop keeps counting past a taken name rather than overwriting it
        assert g.superseded_path(out).name == 'results.superseded-20261111T162721Z-3'
    finally:
        for restore in reversed(restores):
            restore()
    assert code == 0, output
    assert (taken / 'keep.json').read_text(encoding='utf-8') == 'older run'
    assert second.name == 'results.superseded-20261111T162721Z-2'
    assert (second / 'ordinary.json').read_text(encoding='utf-8') == 'newer stale verdict'
