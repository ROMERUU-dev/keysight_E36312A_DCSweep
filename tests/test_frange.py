from src.measurements.dc_sweep import generate_sweep_values, is_in_compliance


def test_generate_sweep_values_includes_stop() -> None:
    assert generate_sweep_values(0.0, 1.0, 0.25) == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_generate_sweep_values_descending() -> None:
    assert generate_sweep_values(1.0, 0.0, 0.4) == [1.0, 0.6, 0.2, 0.0]


def test_generate_sweep_values_rejects_zero_step() -> None:
    try:
        generate_sweep_values(0.0, 1.0, 0.0)
    except ValueError as exc:
        assert "non-zero" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_compliance_tolerance() -> None:
    assert is_in_compliance(0.099, 0.1, 0.02)
    assert not is_in_compliance(0.090, 0.1, 0.02)
