from datetime import datetime, timedelta, timezone

import pytest

from lib.comfort import (
    ActionType,
    LastState,
    Mode,
    calculate_discomfort_index,
    decide_action,
    invert_discomfort_index,
)


def test_calculate_discomfort_index():
    assert calculate_discomfort_index(25, 50) == pytest.approx(71.775)


def test_invert_discomfort_index_round_trips_calculate_discomfort_index():
    di = calculate_discomfort_index(25, 50)
    assert invert_discomfort_index(di, 50) == pytest.approx(25)


def test_decide_action_lower_temp_when_above_range():
    state = LastState(last_set_temp=None, last_action_at=None)
    decision = decide_action(
        80, 50, state, datetime.now(timezone.utc),
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=99, humidity_deadband=5,
    )
    assert decision.action == ActionType.LOWER_TEMP
    assert decision.new_temp == round(invert_discomfort_index(67.5, 50))
    assert decision.pending_target_di == calculate_discomfort_index(decision.new_temp, 50)
    assert decision.correction_offset == 0.0


def test_decide_action_raise_temp_when_below_range():
    state = LastState(last_set_temp=None, last_action_at=None)
    decision = decide_action(
        50, 50, state, datetime.now(timezone.utc),
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=99, humidity_deadband=5,
    )
    assert decision.action == ActionType.RAISE_TEMP
    assert decision.new_temp == round(invert_discomfort_index(67.5, 50))
    assert decision.pending_target_di == calculate_discomfort_index(decision.new_temp, 50)


def test_decide_action_noop_within_range():
    state = LastState(last_set_temp=None, last_action_at=None)
    decision = decide_action(
        65, 50, state, datetime.now(timezone.utc),
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=99, humidity_deadband=5,
    )
    assert decision.action == ActionType.NOOP
    assert decision.new_temp is None


def test_decide_action_noop_during_cooldown_and_skips_learning():
    now = datetime.now(timezone.utc)
    state = LastState(
        last_set_temp=25, last_action_at=now - timedelta(minutes=5),
        last_target_di=68.0, correction_offset=1.2,
    )
    decision = decide_action(
        80, 50, state, now,
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=99, humidity_deadband=5,
    )
    assert decision.action == ActionType.NOOP
    assert decision.new_temp is None
    assert decision.correction_offset == 1.2
    assert decision.pending_target_di == 68.0


def test_decide_action_acts_after_cooldown_elapsed_without_pending_prediction():
    now = datetime.now(timezone.utc)
    state = LastState(last_set_temp=25, last_action_at=now - timedelta(minutes=20))
    decision = decide_action(
        80, 50, state, now,
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=99, humidity_deadband=5,
    )
    assert decision.action == ActionType.LOWER_TEMP
    assert decision.correction_offset == 0.0
    assert decision.new_temp == 24
    assert decision.pending_target_di == calculate_discomfort_index(24, 50)


def test_decide_action_learns_correction_offset_and_consumes_pending_target():
    now = datetime.now(timezone.utc)
    state = LastState(
        last_set_temp=25, last_action_at=now - timedelta(minutes=20),
        last_target_di=70.0, correction_offset=0.0,
    )
    decision = decide_action(
        74, 50, state, now,
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=99, humidity_deadband=5,
    )
    slope = 0.81 + 0.0099 * 50
    expected_offset = -0.3 * ((74 - 70) / slope)

    assert decision.action == ActionType.NOOP
    assert decision.correction_offset == pytest.approx(expected_offset)
    assert decision.pending_target_di is None


def test_decide_action_clamps_correction_offset_to_max():
    now = datetime.now(timezone.utc)
    state = LastState(
        last_set_temp=25, last_action_at=now - timedelta(minutes=20),
        last_target_di=40.0, correction_offset=0.0,
    )
    decision = decide_action(
        90, 50, state, now,
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=99, humidity_deadband=5,
    )
    assert decision.correction_offset == -5.0
    assert decision.action == ActionType.LOWER_TEMP
    assert decision.new_temp == 24
    assert decision.pending_target_di == calculate_discomfort_index(24, 50)


def test_decide_action_steps_down_by_at_most_step_max():
    state = LastState(last_set_temp=25, last_action_at=None)
    decision = decide_action(
        80, 50, state, datetime.now(timezone.utc),
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=99, humidity_deadband=5,
    )
    assert decision.action == ActionType.LOWER_TEMP
    assert decision.new_temp == 24
    assert decision.pending_target_di == calculate_discomfort_index(24, 50)
    assert decision.pending_target_di != 67.5


def test_decide_action_steps_up_by_at_most_step_max():
    state = LastState(last_set_temp=19, last_action_at=None)
    decision = decide_action(
        50, 50, state, datetime.now(timezone.utc),
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=99, humidity_deadband=5,
    )
    assert decision.action == ActionType.RAISE_TEMP
    assert decision.new_temp == 20
    assert decision.pending_target_di == calculate_discomfort_index(20, 50)


def test_decide_action_first_action_skips_step_limiting():
    state = LastState(last_set_temp=None, last_action_at=None)
    decision = decide_action(
        80, 50, state, datetime.now(timezone.utc),
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=99, humidity_deadband=5,
    )
    assert decision.new_temp == round(invert_discomfort_index(67.5, 50))
    assert decision.pending_target_di == calculate_discomfort_index(decision.new_temp, 50)


def test_decide_action_noop_when_already_at_ideal_temp_but_still_learns():
    now = datetime.now(timezone.utc)
    ideal_temp = round(invert_discomfort_index(67.5, 50))
    state = LastState(
        last_set_temp=ideal_temp, last_action_at=now - timedelta(minutes=20),
        last_target_di=None, correction_offset=0.0,
    )
    decision = decide_action(
        80, 50, state, now,
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=99, humidity_deadband=5,
    )
    assert decision.action == ActionType.NOOP
    assert decision.new_temp is None
    assert decision.pending_target_di == calculate_discomfort_index(ideal_temp, 50)


def test_decide_action_switches_to_dry_when_humidity_exceeds_threshold():
    state = LastState(last_set_temp=25, last_action_at=None, mode=Mode.COOL)
    decision = decide_action(
        65, 70, state, datetime.now(timezone.utc),
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=60, humidity_deadband=5,
    )
    assert decision.action == ActionType.SWITCH_TO_DRY
    assert decision.new_mode == Mode.DRY
    assert decision.new_temp == 25
    assert decision.pending_target_di is None


def test_decide_action_stays_in_current_mode_within_hysteresis_band():
    state = LastState(last_set_temp=25, last_action_at=None, mode=Mode.DRY)
    decision = decide_action(
        65, 58, state, datetime.now(timezone.utc),
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=60, humidity_deadband=5,
    )
    assert decision.action == ActionType.NOOP
    assert decision.new_mode is None


def test_decide_action_switches_back_to_cool_when_humidity_drops_below_lower_threshold():
    state = LastState(last_set_temp=25, last_action_at=None, mode=Mode.DRY)
    decision = decide_action(
        65, 50, state, datetime.now(timezone.utc),
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=1, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=60, humidity_deadband=5,
    )
    assert decision.action == ActionType.SWITCH_TO_COOL
    assert decision.new_mode == Mode.COOL
    assert decision.new_temp == 25
    assert decision.pending_target_di is None


def test_decide_action_mode_switch_computes_temp_and_skips_learning_even_when_di_out_of_range():
    state = LastState(last_set_temp=25, last_action_at=None, mode=Mode.COOL)
    decision = decide_action(
        80, 70, state, datetime.now(timezone.utc),
        di_target_min=60, di_target_max=75, di_deadband=2, cooldown_minutes=15,
        temp_min=20, temp_max=28, temp_step_max=10, correction_learning_rate=0.3, correction_max_offset=5,
        humidity_target_max=60, humidity_deadband=5,
    )
    assert decision.action == ActionType.SWITCH_TO_DRY
    assert decision.new_mode == Mode.DRY
    assert decision.new_temp == round(invert_discomfort_index(67.5, 70))
    assert decision.pending_target_di is None
