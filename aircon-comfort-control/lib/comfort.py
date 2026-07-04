"""不快指数の計算と、エアコン操作の判定ロジック。外部I/Oを持たない純粋関数のみで構成する。"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class ActionType(str, Enum):
    RAISE_TEMP = "raise_temp"
    LOWER_TEMP = "lower_temp"
    SWITCH_TO_DRY = "switch_to_dry"
    SWITCH_TO_COOL = "switch_to_cool"
    NOOP = "noop"


class Mode(str, Enum):
    COOL = "cool"
    DRY = "dry"


@dataclass
class LastState:
    last_set_temp: float | None
    last_action_at: datetime | None
    last_target_di: float | None = None
    correction_offset: float = 0.0
    mode: Mode = Mode.COOL


@dataclass
class Decision:
    action: ActionType
    new_temp: int | None
    new_mode: Mode | None
    correction_offset: float
    pending_target_di: float | None


def calculate_discomfort_index(temp_c: float, rh_percent: float) -> float:
    """不快指数(DI) = 0.81T + 0.01H(0.99T - 14.3) + 46.3"""
    return 0.81 * temp_c + 0.01 * rh_percent * (0.99 * temp_c - 14.3) + 46.3


def invert_discomfort_index(target_di: float, rh_percent: float) -> float:
    """calculate_discomfort_indexをTについて解き、目標DIを実現する温度を求める。"""
    return (target_di - 46.3 + 0.143 * rh_percent) / (0.81 + 0.0099 * rh_percent)


def decide_action(
    current_di: float,
    humidity_percent: float,
    last_state: LastState,
    now: datetime,
    di_target_min: float,
    di_target_max: float,
    di_deadband: float,
    cooldown_minutes: int,
    temp_min: int,
    temp_max: int,
    temp_step_max: int,
    correction_learning_rate: float,
    correction_max_offset: float,
    humidity_target_max: float,
    humidity_deadband: float,
) -> Decision:
    """今の気温・湿度から目標不快指数を実現する温度と、湿度に応じた運転モードを毎回直接計算する。

    前回の操作結果(クールダウン明け後の実測DI)と、その時に狙っていた目標DIとの
    ズレから補正量(correction_offset)を学習し、以降の温度計算に反映する。
    モード切替(COOL/DRY)を伴ったサイクルでは、湿度側の変化がDIに混入するため
    pending_target_diをNoneのまま返し、次サイクルの補正量学習をスキップする。
    """
    correction_offset = last_state.correction_offset
    pending_target_di = last_state.last_target_di

    if last_state.last_action_at is not None:
        elapsed = now - last_state.last_action_at
        if elapsed < timedelta(minutes=cooldown_minutes):
            return Decision(ActionType.NOOP, None, None, correction_offset, pending_target_di)

        if pending_target_di is not None:
            slope = 0.81 + 0.0099 * humidity_percent
            di_error = current_di - pending_target_di
            implied_temp_error = di_error / slope
            correction_offset -= correction_learning_rate * implied_temp_error
            correction_offset = max(-correction_max_offset, min(correction_max_offset, correction_offset))
            pending_target_di = None

    if last_state.mode == Mode.COOL and humidity_percent > humidity_target_max + humidity_deadband:
        desired_mode = Mode.DRY
    elif last_state.mode == Mode.DRY and humidity_percent < humidity_target_max - humidity_deadband:
        desired_mode = Mode.COOL
    else:
        desired_mode = last_state.mode

    di_out_of_range = current_di > di_target_max + di_deadband or current_di < di_target_min - di_deadband

    target_di = (di_target_min + di_target_max) / 2
    ideal_temp = invert_discomfort_index(target_di, humidity_percent) + correction_offset
    ideal_new_temp = round(max(temp_min, min(temp_max, ideal_temp)))

    if last_state.last_set_temp is None:
        candidate_temp = ideal_new_temp
    else:
        diff = ideal_new_temp - last_state.last_set_temp
        step = max(-temp_step_max, min(temp_step_max, diff))
        candidate_temp = round(last_state.last_set_temp + step)

    if di_out_of_range or last_state.last_set_temp is None:
        new_temp = candidate_temp
    else:
        new_temp = last_state.last_set_temp

    if desired_mode != last_state.mode:
        action = ActionType.SWITCH_TO_DRY if desired_mode == Mode.DRY else ActionType.SWITCH_TO_COOL
        return Decision(action, new_temp, desired_mode, correction_offset, None)

    if di_out_of_range:
        pending_target_di = calculate_discomfort_index(new_temp, humidity_percent)

        if last_state.last_set_temp is not None and new_temp == last_state.last_set_temp:
            return Decision(ActionType.NOOP, None, None, correction_offset, pending_target_di)

        action = ActionType.LOWER_TEMP if current_di > di_target_max + di_deadband else ActionType.RAISE_TEMP
        return Decision(action, new_temp, None, correction_offset, pending_target_di)

    return Decision(ActionType.NOOP, None, None, correction_offset, pending_target_di)
