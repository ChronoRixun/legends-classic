"""G8 comparator (tools/loot_compare.py): both log dialects, roll grouping, enemy-minutes, the +/-20 percent gate, the
exit codes. Synthetic logs generated here from an invented drop model; no game data and no real logs."""
import json
import random
import tempfile
from pathlib import Path

import loot_compare as LC


# ---------------------------------------------------------------------------------------------------- synthetic logs
def outcome(rng, model):
    """one kill's drops: [(definition, amount)] ([] = nothing). model: any drop / gear / pack / xtreme-of-fallback."""
    if rng.random() >= model['any']:
        return []
    x = rng.random()
    if x < model['gear']:
        return [(f'lc_x1_item_{rng.randint(1, 40)}', 1)]
    x -= model['gear']
    if x < model['pack']:
        return [(rng.choice(('HEALTH_ITEM', 'ENERGY_ITEM')), 1)]
    if rng.random() < model['xtreme']:
        return [('XTREME_PIP', 1)]
    money = f'MONEY{rng.randint(1, 3)}'
    return [(money, 17)] * rng.randint(2, 4)


# the first game's nominal per-kill rates for an ordinary actor: any drop 45 %, gear 3.15, pack 26.1, fallback 15.75
XML1 = dict(any=0.45, gear=3.15 / 45, pack=26.1 / 45, xtreme=0.4)
# the port before this work: any drop 65 %, gear 3.25, pack 16.25, money / Xtreme 45.5
XML2 = dict(any=0.65, gear=3.25 / 65, pack=16.25 / 65, xtreme=0.1)


def make_run(seed, model, rolls=4000, cat=3, pace=1.3):
    """[(t, cat, lead, [(def, amt)])]: `rolls` kills, `pace` seconds apart on average"""
    rng = random.Random(seed)
    t, out = 0.0, []
    for _ in range(rolls):
        t += rng.uniform(0.5, 2 * pace - 0.5)
        out.append((round(t, 3), cat, 0, outcome(rng, model)))
    return out


def s6_lines(run, rid='orig', minutes=None, serial=True):
    mins = minutes if minutes is not None else run[-1][0] / 60.0
    lines = [f'run id={rid} game=xbe zone=invented enemy_minutes={mins:.4f}']
    for n, (t, cat, lead, drops) in enumerate(run, 1):
        lines.append(f'roll t={t:.3f} cat={cat} lead={lead}' + (f' n={n}' if serial else ''))
        for name, amt in drops:
            lines.append(f'spawn t={t:.3f} def={name} amt={amt}' + (f' n={n}' if serial else ''))
    return lines


def stamp(t):
    t = 10 * 3600 + 20 * 60 + t
    return f'[{int(t // 3600) % 24:02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}.{int(round((t % 1) * 1000)) % 1000:03d}] '


def port_lines(run, rid='port', minutes=None, stamps=True):
    lines = []
    if minutes is not None:
        lines.append(f'run id={rid} game=port zone=invented enemy_minutes={minutes:.4f}')
    for t, cat, lead, drops in run:
        head = (stamp(t) if stamps else '') + f'roll cat={cat} lead={lead} G=2 bucket=3 '
        if not drops:
            lines.append(head + 'def=- amt=0 draws=1')
        for name, amt in drops:
            lines.append(head + f'def={name} amt={amt} draws=7')
    return lines


def runs_from(side, seeds, model, **kw):
    out = []
    for i, seed in enumerate(seeds):
        run = make_run(seed, model, **kw)
        mins = run[-1][0] / 60.0
        lines = s6_lines(run, f'o{i}', mins) if side == 's6' else port_lines(run, f'p{i}', mins)
        out.append(LC.parse_lines(lines, side, source=f'{side}{i}')[0].finish())
    return out


# ---------------------------------------------------------------------------------------------------- classification
def test_classification_by_definition_name():
    c = LC.classify
    assert [c('MONEY1'), c('money3'), c('XTREME_PIP'), c('HEALTH_ITEM'), c('energy_item')] == \
        ['money', 'money', 'xtreme', 'pack', 'pack']
    assert [c('SKIRMISH_KING_PIP'), c('KEY2'), c('keycard1'), c('XP')] == ['other'] * 4
    assert [c('lc_x1_wolverines_claws'), c('ARMOR1'), c('belt_std_lgt')] == ['gear'] * 3


# ---------------------------------------------------------------------------------------------------- port grouping
def test_port_pickups_of_one_roll_are_one_roll_and_one_event_per_class():
    lines = [
        '[10:00:00.100] roll cat=3 lead=0 G=1 bucket=0 def=- amt=0 draws=1',                  # nothing
        '[10:00:01.000] roll cat=3 lead=0 G=1 bucket=3 def=HEALTH_ITEM amt=1 draws=4',        # a pack
        '[10:00:01.900] roll cat=3 lead=0 G=1 bucket=3 def=HEALTH_ITEM amt=1 draws=4',        # the same again: a new roll
        '[10:00:02.500] roll cat=3 lead=0 G=1 bucket=0 def=MONEY2 amt=12 draws=3',            # a money drop of 3 pickups
        '[10:00:02.500] roll cat=3 lead=0 G=1 bucket=0 def=MONEY2 amt=12 draws=3',
        '[10:00:02.501] roll cat=3 lead=0 G=1 bucket=0 def=MONEY2 amt=12 draws=3',
        '[10:00:03.800] roll cat=3 lead=0 G=1 bucket=0 def=MONEY2 amt=12 draws=3',            # equal header, 1.3 s later
        '[10:00:03.800] roll cat=3 lead=0 G=1 bucket=0 def=MONEY2 amt=12 draws=3',
        '[10:00:05.000] roll cat=5 lead=1 G=1 bucket=2 def=lc_x1_a amt=1 draws=6',            # a leader: gear + 3 more
        '[10:00:05.002] roll cat=5 lead=1 G=1 bucket=2 def=HEALTH_ITEM amt=1 draws=6',
        '[10:00:05.004] roll cat=5 lead=1 G=1 bucket=2 def=XTREME_PIP amt=1 draws=6',
        '[10:00:05.004] roll cat=5 lead=1 G=1 bucket=2 def=XTREME_PIP amt=1 draws=6',
    ]
    run = LC.parse_lines(lines, 'port', 'unit')[0]
    assert [len(r.drops) for r in run.rolls] == [0, 1, 1, 3, 2, 4]
    run.finish()
    m = LC.run_metrics(run)
    assert m['rolls'] == 6 and m['rolls_with_drop'] == 5 and m['drops'] == 11
    # events: pack 2 + 1, money 1 + 1, gear 1, xtreme 1 (the leader's two pips are one event)
    assert m['events'] == {'gear': 1, 'pack': 3, 'money': 2, 'xtreme': 1, 'other': 0}
    assert m['pickups']['money'] == 5 and m['drop_events'] == 7
    assert run.ambiguous_merges == 0 and run.minutes_source == 'derived'
    assert abs(run.minutes * 60 - 4.9) < 1e-6                                       # first roll at 00.100, last roll starts 05.000


def test_pipe_output_without_timestamps_merges_equal_money_rolls_and_says_so():
    lines = ['roll cat=3 lead=0 G=1 bucket=0 def=MONEY1 amt=9 draws=3'] * 5 + \
            ['roll cat=3 lead=0 G=1 bucket=3 def=HEALTH_ITEM amt=1 draws=4']
    run = LC.parse_lines(lines, 'port', 'pipe')[0]
    run.minutes = 2.0
    run.finish()
    assert [len(r.drops) for r in run.rolls] == [5, 1]                 # cannot be told apart: merged
    assert run.ambiguous_merges == 1
    res = LC.run_compare([run] * 3, [run] * 3)
    assert any('merged pickups without timestamps' in n for n in res['notes'])


def test_pipe_history_and_log_lines_parse_alike():
    log = ['[01:02:03.004] roll cat=3 lead=0 G=2 bucket=2 def=lc_x1_a amt=1 draws=5',
           '[01:02:04.100] roll cat=3 lead=0 G=2 bucket=0 def=- amt=0 draws=1']
    pipe = [l.split('] ', 1)[1] for l in log]
    a = LC.parse_lines(log, None, 'log')[0]
    b = LC.parse_lines(pipe, None, 'pipe')[0]
    assert [(r.cat, r.lead, r.drops) for r in a.rolls] == [(r.cat, r.lead, r.drops) for r in b.rolls]
    assert a.side == 'port' == b.side and a.rolls[0].t is not None and b.rolls[0].t is None


# ---------------------------------------------------------------------------------------------------- S6 dialect
def test_s6_headers_serials_class_override_and_several_runs_per_file():
    lines = [
        '# a comment, ignored', 'something else entirely',
        'run id=a zone=nyc1 enemy_minutes=2.5',
        'roll t=10.0 cat=3 lead=0 n=1', 'roll t=11.0 cat=3 lead=1 n=2',
        'spawn t=11.0 def=XTREME_PIP amt=1 n=2', 'spawn t=10.0 def=MONEY3 amt=20 n=1', 'spawn t=10.0 def=MONEY3 amt=20 n=1',
        'run id=b zone=nyc1', 'roll t=1 cat=0 lead=0', 'spawn t=1 def=ODD_THING amt=1 cls=other',
    ]
    runs = LC.parse_lines(lines, 's6', 'file')
    assert [r.id for r in runs] == ['a', 'b'] and runs[0].minutes == 2.5 and runs[0].side == 's6'
    a = runs[0]
    assert [(r.cat, r.lead, [d[0] for d in r.drops]) for r in a.rolls] == [(3, 0, ['MONEY3', 'MONEY3']), (3, 1, ['XTREME_PIP'])]
    assert runs[1].rolls[0].drops == [('ODD_THING', 1, 'other')]
    a.finish()
    assert a.minutes_source == 'header'
    try:
        LC.parse_lines(['spawn t=1 def=MONEY1 amt=1'], 's6', 'x')
        raise AssertionError('a spawn before any roll was accepted')
    except LC.LogError as e:
        assert 'before any roll' in str(e)


# ---------------------------------------------------------------------------------------------------- enemy-minutes
def test_enemy_minutes_header_override_derived_and_the_midnight_wrap():
    lines = ['[23:59:30.000] roll cat=3 lead=0 G=1 bucket=0 def=- amt=0 draws=1',
             '[00:00:30.000] roll cat=3 lead=0 G=1 bucket=0 def=- amt=0 draws=1']
    run = LC.parse_lines(lines, 'port', 'wrap')[0]
    run.finish()
    assert run.minutes_source == 'derived' and abs(run.minutes - 1.0) < 1e-9          # 60 s across midnight
    run2 = LC.parse_lines(['run id=h enemy_minutes=4'] + lines, 'port', 'wrap')[0]
    assert run2.finish().minutes == 4.0 and run2.minutes_source == 'header'
    assert LC.parse_lines(['run id=h enemy_minutes=4'] + lines, 'port', 'w')[0].finish(7).minutes == 7.0
    bare = LC.parse_lines(['roll cat=3 lead=0 G=1 bucket=0 def=- amt=0 draws=1'], 'port', 'bare')[0]
    try:
        bare.finish()
        raise AssertionError('a run without any enemy-minutes was accepted')
    except LC.LogError as e:
        assert 'enemy-minutes' in str(e)


# ---------------------------------------------------------------------------------------------------- the gate
def test_the_same_model_passes_and_both_dialects_agree():
    s6 = runs_from('s6', (1, 2, 3), XML1)
    port = runs_from('port', (11, 12, 13), XML1)
    res = LC.run_compare(s6, port)
    assert res['verdict'] == 'PASS' and not res['failing'] and not res['problems'], LC.render(res)
    assert all(r['pass'] for r in res['rows']) and all(not r['underpowered'] for r in res['rows'])
    # the same synthetic runs rendered in the other dialect measure the same pooled numbers
    again = runs_from('port', (1, 2, 3), XML1)
    a, b = LC.pooled(s6), LC.pooled(again)
    assert a['rolls'] == b['rolls'] and a['drops'] == b['drops'] and a['events'] == b['events']
    nominal = res['pooled']['original']
    assert abs(nominal['mix']['pack'] - 26.1 / 45) < 0.03 and abs(nominal['events_per_roll'] - 0.45) < 0.02
    text = LC.render(res)
    assert 'G8 VERDICT: PASS' in text and 'POOLED' in text and 'ORIGINAL runs' in text and 'PORT RUNS' in text


def test_the_port_before_the_change_fails_on_the_drop_rate():
    res = LC.run_compare(runs_from('s6', (1, 2, 3), XML1), runs_from('port', (4, 5, 6), XML2))
    assert res['verdict'] == 'FAIL'
    rate = res['rows'][0]
    assert rate['metric'] == 'drop events per enemy-minute' and not rate['pass'] and 0.35 < rate['relative'] < 0.55
    assert 'drop events per enemy-minute' in res['failing'] and not res['port_runs_vs_original_pool'][0]['pass']
    assert 'G8 VERDICT: FAIL (failing:' in LC.render(res)


def test_every_mix_row_fails_independently_at_the_tolerance():
    s6 = runs_from('s6', (1, 2, 3), XML1)
    # a pack share 30 % too high: the pack row fails (the other shares shrink with it), the drop rate does not move
    heavy = dict(XML1, pack=XML1['pack'] * 1.3)
    res = LC.run_compare(s6, runs_from('port', (7, 8, 9), heavy))
    pack = next(r for r in res['rows'] if r['metric'] == 'mix: pack')
    assert not pack['pass'] and pack['relative'] > 0.2
    assert next(r for r in res['rows'] if r['metric'] == 'drop events per enemy-minute')['pass']     # the rate is the original's
    # no gear at all: the gear row fails and says -100 %
    nogear = dict(XML1, gear=0.0)
    res = LC.run_compare(s6, runs_from('port', (7, 8, 9), nogear))
    gear = next(r for r in res['rows'] if r['metric'] == 'mix: gear')
    assert not gear['pass'] and abs(gear['relative'] + 1.0) < 1e-9 and 'mix: gear' in res['failing']
    # a looser tolerance lets the 30 % heavier pack share (and the shrunken others) through
    res = LC.run_compare(s6, runs_from('port', (7, 8, 9), heavy), tolerance=0.6)
    assert all(r['pass'] for r in res['rows'])


def test_fewer_than_the_required_runs_fails_and_short_runs_are_flagged_underpowered():
    s6 = runs_from('s6', (1, 2), XML1)
    port = runs_from('port', (4, 5), XML1)
    res = LC.run_compare(s6, port)
    assert res['verdict'] == 'FAIL' and len(res['problems']) == 2 and not res['failing']
    assert LC.run_compare(s6, port, min_runs=2)['verdict'] == 'PASS'
    tiny_s6 = runs_from('s6', (1, 2, 3), XML1, rolls=60)
    tiny_port = runs_from('port', (4, 5, 6), XML1, rolls=60)
    res = LC.run_compare(tiny_s6, tiny_port)
    assert 'mix: gear' in res['underpowered'] and 'UNDERPOWERED' in LC.render(res)


def test_a_zero_original_share_is_infinite_not_a_crash():
    s6 = runs_from('s6', (1, 2, 3), dict(XML1, gear=0.0))
    res = LC.run_compare(s6, runs_from('port', (4, 5, 6), XML1))
    gear = next(r for r in res['rows'] if r['metric'] == 'mix: gear')
    assert not gear['pass'] and gear['relative'] == float('inf')
    assert json.dumps(LC._clean(res))                                     # serialisable: infinities become null
    assert LC.render(res)


# ---------------------------------------------------------------------------------------------------- command line
def test_cli_exit_codes_json_and_input_errors():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        def write(name, lines):
            p = d / name
            p.write_text('\n'.join(lines) + '\n', encoding='ascii')
            return str(p)
        s6 = [write(f's6_{i}.log', s6_lines(make_run(i, XML1), f'o{i}')) for i in (1, 2, 3)]
        ok = [write(f'port_{i}.log', port_lines(make_run(10 + i, XML1), f'p{i}')) for i in (1, 2, 3)]
        bad = [write(f'bad_{i}.log', port_lines(make_run(20 + i, XML2), f'q{i}')) for i in (1, 2, 3)]
        out = str(d / 'result.json')
        assert LC.main(['--s6', *s6, '--port', *ok, '--json', out]) == 0
        data = json.loads(Path(out).read_text(encoding='utf-8'))
        assert data['verdict'] == 'PASS' and len(data['runs']['port']) == 3 and data['pooled']['port']['rolls'] == 12000
        assert LC.main(['--s6', *s6, '--port', *bad]) == 1
        assert LC.main(['--s6', *s6, '--port', str(d / 'missing.log')]) == 2
        empty = write('empty.log', ['nothing useful here'])
        assert LC.main(['--s6', *s6, '--port', empty]) == 2
        # no minutes anywhere in a pipe dump: an input error, then fixed with --minutes-port
        pipe = [write(f'pipe_{i}.log', [l.split('] ', 1)[1] for l in port_lines(make_run(30 + i, XML1))]) for i in (1, 2, 3)]
        assert LC.main(['--s6', *s6, '--port', *pipe]) == 2
        mins = ','.join(str(make_run(30 + i, XML1)[-1][0] / 60.0) for i in (1, 2, 3))
        assert LC.main(['--s6', *s6, '--port', *pipe, '--minutes-port', mins]) == 0
        assert LC.main(['--s6', *s6, '--port', *pipe, '--minutes-port', '1,2']) == 2


# ---------------------------------------------------------------------------------------------------- roll serial n=
def _money_rolls_10ms(serial):
    """the reviewer's reproduction: two rolls, each three MONEY1 pickups, the second 10 ms after the first"""
    lines = []
    for i, base in enumerate((100, 110)):
        for _ in range(3):
            n = f' n={i + 1}' if serial else ''
            lines.append(f'[10:00:00.{base}] roll{n} cat=3 lead=0 G=1 bucket=0 def=MONEY1 amt=9 draws=3')
    return lines


def test_serial_keeps_back_to_back_money_rolls_apart():
    run = LC.parse_lines(_money_rolls_10ms(True), 'port', 'unit')[0]
    assert [len(r.drops) for r in run.rolls] == [3, 3]
    assert run.warnings == [] and run.ambiguous_merges == 0
    m = LC.run_metrics(run.finish(1.0))
    assert m['rolls'] == 2 and m['events']['money'] == 2 and m['drops'] == 6


def test_without_serial_the_same_log_is_warned_about_not_silently_merged():
    run = LC.parse_lines(_money_rolls_10ms(False), 'port', 'unit')[0]
    assert [len(r.drops) for r in run.rolls] == [6]                     # the window cannot tell them apart ...
    assert any('more than 4 pickups' in w for w in run.warnings)         # ... and says so
    res = LC.run_compare([run.finish(1.0)] * 3, [run] * 3)
    assert any('more than 4 pickups' in w for w in res['warnings'])
    assert any('no n=<serial>' in w for w in res['warnings'])
    assert 'WARNING: ' in LC.render(res)


def test_serial_groups_by_n_not_by_time_or_adjacency():
    lines = ['[10:00:00.000] roll n=7 cat=3 lead=0 G=1 bucket=0 def=MONEY1 amt=9 draws=3',
             '[10:00:00.001] roll n=8 cat=3 lead=0 G=1 bucket=0 def=MONEY1 amt=9 draws=3',   # interleaved
             '[10:00:00.002] roll n=7 cat=3 lead=0 G=1 bucket=0 def=MONEY1 amt=9 draws=3',
             '[10:00:00.003] roll n=9 cat=3 lead=0 G=1 bucket=3 def=- amt=0 draws=1',         # nothing
             'roll n=10 cat=5 lead=1 G=1 bucket=2 def=lc_x1_a amt=1 draws=6',                  # pipe line: no timestamp
             'roll n=10 cat=5 lead=1 G=1 bucket=2 def=HEALTH_ITEM amt=1 draws=6']
    run = LC.parse_lines(lines, 'port', 'unit')[0]
    assert [(r.n, len(r.drops)) for r in run.rolls] == [('7', 2), ('8', 1), ('9', 0), ('10', 2)]
    assert run.warnings == [] and run.ambiguous_merges == 0


def test_pipe_output_with_serials_is_exact_and_needs_no_warning():
    lines = ['roll n=%d cat=3 lead=0 G=1 bucket=0 def=MONEY1 amt=9 draws=3' % (i // 3 + 1) for i in range(15)]
    run = LC.parse_lines(lines, 'port', 'pipe')[0]
    assert [len(r.drops) for r in run.rolls] == [3] * 5
    assert run.ambiguous_merges == 0 and run.warnings == []


def test_a_reused_serial_is_a_new_roll_and_warns():
    lines = ['[10:00:00.000] roll n=1 cat=3 lead=0 G=1 bucket=0 def=MONEY1 amt=9 draws=3',
             '[10:00:00.001] roll n=1 cat=3 lead=0 G=1 bucket=0 def=MONEY1 amt=9 draws=3',
             '[10:05:00.000] roll n=1 cat=3 lead=0 G=1 bucket=0 def=MONEY1 amt=9 draws=3',   # restarted counter
             '[10:05:00.001] roll n=1 cat=3 lead=0 G=1 bucket=0 def=MONEY1 amt=9 draws=3',
             '[10:05:09.000] roll n=1 cat=4 lead=0 G=1 bucket=1 def=HEALTH_ITEM amt=1 draws=4']  # other header
    run = LC.parse_lines(lines, 'port', 'unit')[0]
    assert [len(r.drops) for r in run.rolls] == [2, 2, 1]
    assert sum('reused' in w for w in run.warnings) == 2


def test_mixed_serial_and_plain_lines_warn():
    lines = ['[10:00:00.000] roll n=1 cat=3 lead=0 G=1 bucket=3 def=HEALTH_ITEM amt=1 draws=4',
             '[10:00:02.000] roll cat=3 lead=0 G=1 bucket=3 def=HEALTH_ITEM amt=1 draws=4']
    run = LC.parse_lines(lines, 'port', 'unit')[0]
    assert len(run.rolls) == 2 and any('without' in w for w in run.warnings)


def test_serial_results_match_the_window_results_on_unambiguous_logs():
    plain = ['[10:00:01.000] roll cat=3 lead=0 G=1 bucket=3 def=HEALTH_ITEM amt=1 draws=4',
             '[10:00:02.500] roll cat=3 lead=0 G=1 bucket=0 def=MONEY2 amt=12 draws=3',
             '[10:00:02.501] roll cat=3 lead=0 G=1 bucket=0 def=MONEY2 amt=12 draws=3',
             '[10:00:04.000] roll cat=3 lead=0 G=1 bucket=0 def=- amt=0 draws=1']
    ser = [l.replace('roll ', f'roll n={n} ', 1) for l, n in zip(plain, (1, 2, 2, 3))]
    a, b = (LC.parse_lines(x, 'port', 'u')[0].finish(1.0) for x in (plain, ser))
    assert LC.run_metrics(a) == LC.run_metrics(b) and a.warnings == [] == b.warnings
