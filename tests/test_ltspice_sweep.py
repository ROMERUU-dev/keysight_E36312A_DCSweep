import pytest

from src.measurements.ltspice_dc_sweep import (
    SweepSource,
    generate_dc_directive,
    generate_nested_sweep_points,
    generate_sweep_values,
    parse_values_list,
)


def test_linear_ascending() -> None:
    source = SweepSource(name="VIN", channel="CH1", start=0, stop=1, increment=0.5)
    assert generate_sweep_values(source) == [0, 0.5, 1.0]


def test_linear_descending() -> None:
    source = SweepSource(name="VIN", channel="CH1", start=1, stop=0, increment=-0.5)
    assert generate_sweep_values(source) == [1, 0.5, 0]


def test_increment_zero_fails() -> None:
    source = SweepSource(name="VIN", channel="CH1", start=0, stop=1, increment=0)
    with pytest.raises(ValueError):
        generate_sweep_values(source)


def test_decade_start_le_zero_fails() -> None:
    source = SweepSource(
        name="VIN",
        channel="CH1",
        sweep_type="decade",
        start=0,
        stop=1,
        points_per_decade=10,
    )
    with pytest.raises(ValueError):
        generate_sweep_values(source)


def test_list_parsing() -> None:
    assert parse_values_list("0, 0.1, 0.2 0.5\n1") == [0, 0.1, 0.2, 0.5, 1]


def test_nested_two_source_order() -> None:
    source1 = SweepSource(name="VDS", channel="CH1", start=0, stop=1, increment=1)
    source2 = SweepSource(name="VGS", channel="CH2", start=0, stop=2, increment=2)
    assert generate_nested_sweep_points([source1, source2]) == [
        {"VDS": 0, "VGS": 0},
        {"VDS": 1, "VGS": 0},
        {"VDS": 0, "VGS": 2},
        {"VDS": 1, "VGS": 2},
    ]


def test_nested_three_source_order() -> None:
    source1 = SweepSource(name="VDS", channel="CH1", start=0, stop=1, increment=1)
    source2 = SweepSource(name="VGS", channel="CH2", start=0, stop=2, increment=2)
    source3 = SweepSource(name="VBS", channel="CH3", start=0, stop=3, increment=3)
    assert generate_nested_sweep_points([source1, source2, source3]) == [
        {"VDS": 0, "VGS": 0, "VBS": 0},
        {"VDS": 1, "VGS": 0, "VBS": 0},
        {"VDS": 0, "VGS": 2, "VBS": 0},
        {"VDS": 1, "VGS": 2, "VBS": 0},
        {"VDS": 0, "VGS": 0, "VBS": 3},
        {"VDS": 1, "VGS": 0, "VBS": 3},
        {"VDS": 0, "VGS": 2, "VBS": 3},
        {"VDS": 1, "VGS": 2, "VBS": 3},
    ]


def test_dc_directive_generation() -> None:
    source1 = SweepSource(name="VDS", channel="CH1", start=0, stop=5, increment=0.1)
    source2 = SweepSource(name="VGS", channel="CH2", start=0, stop=3.3, increment=0.1)
    assert generate_dc_directive([source1, source2]) == ".dc VDS 0 5 0.1 VGS 0 3.3 0.1"
