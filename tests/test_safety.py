import pytest

from src.measurements.safety import SafetyError, SafetyLimits


def test_voltage_limit_accepts_safe_value() -> None:
    SafetyLimits().validate_voltage("CH1", 5.0)


def test_voltage_limit_rejects_overvoltage() -> None:
    with pytest.raises(SafetyError):
        SafetyLimits().validate_voltage("CH1", 7.0)


def test_current_limit_rejects_overcurrent() -> None:
    with pytest.raises(SafetyError):
        SafetyLimits().validate_current("CH2", 2.0)


def test_power_limit_rejects_excess_power() -> None:
    limits = SafetyLimits(
        max_power_by_channel={"CH1": 1.0, "CH2": 25.0, "CH3": 25.0}
    )
    with pytest.raises(SafetyError):
        limits.validate_power("CH1", 2.0, 1.0)
