"""Characterization from the cadence investigation, plus the closed V45 gap.

The independent schedule model explains why static division cannot implement
the contract. Native companion tests exercise actual admission and draw order.
"""
from test_weapon_trace import fixture, errors


def admitted(times, interval, last=-100.0):
    result = []
    for time in times:
        if time - last >= interval:
            result.append(time)
            last = time
    return result


def test_cluster_is_not_seven_independent_damage_draws():
    assert admitted([10., 10.1, 10.2, 10.3, 10.4, 10.5, 10.7], .65) == [10., 10.7]


def test_previous_move_changes_the_same_authored_burst():
    assert admitted([10., 10.1, 10.2, 10.3, 10.4, 10.5, 10.7], .65, last=9.8) == [10.5]


def test_move_reset_cannot_replace_actor_timer():
    assert admitted([10., 10.1], .65) == [10.]
    assert admitted([10.], .65) + admitted([10.1], .65) == [10., 10.1]


def test_static_damage_multiplier_cannot_preserve_both_streams():
    assert len(admitted([10., 11., 12., 13., 14., 15., 16.], .65)) == 7
    assert len(admitted([10., 10.1, 10.2, 10.3, 10.4, 10.5, 10.7], .65)) == 2


def test_v45_refuses_ungated_continuous_beam(tmp_path):
    v, built, _ = fixture(tmp_path)
    for event in built.iter('trigger'):
        event.attrib.pop('split_damage', None)
        event.attrib.pop('split_count', None)
    assert any('trace' in message.lower() for message in errors(v))
