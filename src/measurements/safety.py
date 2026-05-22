from __future__ import annotations

import math
from dataclasses import dataclass, field

from src.utils.units import CHANNELS, normalize_channel


class SafetyError(ValueError):
    """Raised when a requested instrument setting violates configured limits."""


@dataclass(frozen=True)
class SafetyLimits:
    """Conservative default limits for a Keysight E36312A-like 3-channel supply."""

    min_voltage_by_channel: dict[str, float] = field(
        default_factory=lambda: {"CH1": 0.0, "CH2": 0.0, "CH3": 0.0}
    )
    max_voltage_by_channel: dict[str, float] = field(
        default_factory=lambda: {"CH1": 6.0, "CH2": 25.0, "CH3": 25.0}
    )
    max_current_by_channel: dict[str, float] = field(
        default_factory=lambda: {"CH1": 5.0, "CH2": 1.0, "CH3": 1.0}
    )
    max_power_by_channel: dict[str, float] = field(
        default_factory=lambda: {"CH1": 30.0, "CH2": 25.0, "CH3": 25.0}
    )

    def validate_channel(self, channel: str | int) -> str:
        normalized = normalize_channel(channel)
        if normalized not in CHANNELS:
            raise SafetyError(f"Unsupported channel: {channel!r}")
        return normalized

    def validate_voltage(self, channel: str | int, voltage: float) -> None:
        normalized = self.validate_channel(channel)
        if not math.isfinite(voltage):
            raise SafetyError(f"{normalized} voltage must be a finite number")
        minimum = self.min_voltage_by_channel[normalized]
        maximum = self.max_voltage_by_channel[normalized]
        if not minimum <= voltage <= maximum:
            raise SafetyError(
                f"{normalized} voltage {voltage:.6g} V is outside "
                f"the safe range {minimum:.6g} V to {maximum:.6g} V"
            )

    def validate_current(self, channel: str | int, current: float) -> None:
        normalized = self.validate_channel(channel)
        if not math.isfinite(current):
            raise SafetyError(f"{normalized} current limit must be a finite number")
        maximum = self.max_current_by_channel[normalized]
        if current < 0 or current > maximum:
            raise SafetyError(
                f"{normalized} current limit {current:.6g} A is outside "
                f"the safe range 0 A to {maximum:.6g} A"
            )

    def validate_power(self, channel: str | int, voltage: float, current: float) -> None:
        normalized = self.validate_channel(channel)
        if not math.isfinite(voltage) or not math.isfinite(current):
            raise SafetyError(f"{normalized} power calculation requires finite voltage and current")
        maximum = self.max_power_by_channel[normalized]
        power = abs(voltage * current)
        if power > maximum:
            raise SafetyError(
                f"{normalized} requested power {power:.6g} W exceeds "
                f"the safe limit {maximum:.6g} W"
            )

    def validate_setting(self, channel: str | int, voltage: float, current: float) -> None:
        self.validate_voltage(channel, voltage)
        self.validate_current(channel, current)
        self.validate_power(channel, voltage, current)
