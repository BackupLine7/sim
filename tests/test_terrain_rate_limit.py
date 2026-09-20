"""Проверка ограничения скорости изменения высоты земли.

Логика тут короткая, но её поломка не видна: симуляция просто разваливается в
NaN через несколько секунд после старта, без сообщения об ошибке.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sim_launcher.jsbsim_terrain_feeder import JsbSimTerrainFeeder  # noqa: E402
from sim_world.elevation.source import FlatElevationSource  # noqa: E402

UPDATE_PERIOD_S = 0.1
MAX_CHANGE_RATE_M_PER_S = 50.0
MAX_STEP_M = MAX_CHANGE_RATE_M_PER_S * UPDATE_PERIOD_S  # 5 метров за такт


def make_feeder(elevation_asl_m: float) -> JsbSimTerrainFeeder:
    return JsbSimTerrainFeeder(
        host="127.0.0.1",
        command_port=0,
        elevation_source=FlatElevationSource(elevation_asl_m),
        position_provider=lambda: (50.0, 30.0),
        update_period_s=UPDATE_PERIOD_S,
        instance_index=0,
        max_change_rate_m_per_s=MAX_CHANGE_RATE_M_PER_S,
        home_elevation_asl_m=0.0,
    )


def test_startup_does_not_jump_to_airfield_elevation():
    """Самый опасный случай: JSBSim стоит на нуле, аэродром на 179 метрах.

    Без ограничения первая посылка была бы скачком в 179 метров под стоящим
    аппаратом — проверено, что это превращает состояние физики в NaN.
    """
    feeder = make_feeder(179.0)
    first_value_m = feeder._rate_limited(179.0)
    assert first_value_m == MAX_STEP_M, (
        f"первая посылка {first_value_m} м вместо ограниченных {MAX_STEP_M} м"
    )


def test_reaches_target_gradually():
    """Доезжает до нужной высоты, а не застревает по дороге."""
    feeder = make_feeder(179.0)
    value_m = None
    for _ in range(100):  # 10 секунд при такте 0.1 с
        value_m = feeder._rate_limited(179.0)
        feeder._last_sent_elevation_asl_m = value_m
    assert abs(value_m - 179.0) < 0.01, f"застряли на {value_m} м вместо 179"


def test_small_changes_pass_through_untouched():
    """Обычный полёт: земля меняется медленно, ограничение не вмешивается."""
    feeder = make_feeder(200.0)
    feeder._last_sent_elevation_asl_m = 200.0
    assert feeder._rate_limited(202.0) == 202.0
    feeder._last_sent_elevation_asl_m = 202.0
    assert feeder._rate_limited(199.0) == 199.0


def test_descending_terrain_is_limited_too():
    """Обрыв вниз ограничивается так же, как подъём."""
    feeder = make_feeder(0.0)
    feeder._last_sent_elevation_asl_m = 500.0
    assert feeder._rate_limited(0.0) == 500.0 - MAX_STEP_M


if __name__ == "__main__":
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            test()
            print(f"OK  {name}")
    print("Все проверки пройдены")
