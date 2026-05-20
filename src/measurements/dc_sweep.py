from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from src.measurements.safety import SafetyLimits
from src.utils.units import normalize_channel


@dataclass(frozen=True)
class SweepParameters:
    channel: str
    v_start: float
    v_stop: float
    v_step: float
    current_limit: float
    settle_time_s: float
    compliance_tolerance: float = 0.02
    notes: str = ""


@dataclass(frozen=True)
class SweepPoint:
    timestamp_iso: str
    t_s: float
    channel: str
    Vset_V: float
    Vmeas_V: float
    Imeas_A: float
    P_W: float
    compliance_flag: bool
    notes: str = ""


def generate_sweep_values(v_start: float, v_stop: float, v_step: float) -> list[float]:
    if v_step == 0:
        raise ValueError("V_step must be non-zero")

    step = abs(v_step)
    direction = 1.0 if v_stop >= v_start else -1.0
    signed_step = direction * step
    epsilon = max(step * 1e-9, 1e-12)

    values: list[float] = []
    value = float(v_start)
    while direction * (value - v_stop) <= epsilon:
        values.append(round(value, 12))
        value += signed_step
        if len(values) > 100_000:
            raise ValueError("Sweep would generate too many points")

    if not values:
        values.append(round(float(v_start), 12))

    if abs(values[-1] - v_stop) > epsilon:
        values.append(round(float(v_stop), 12))

    return values


def is_in_compliance(current_a: float, current_limit_a: float, tolerance: float) -> bool:
    if current_limit_a <= 0:
        return False
    tolerance = max(0.0, min(0.95, tolerance))
    return abs(current_a) >= abs(current_limit_a) * (1.0 - tolerance)


def validate_sweep(params: SweepParameters, limits: SafetyLimits) -> SweepParameters:
    channel = normalize_channel(params.channel)
    values = generate_sweep_values(params.v_start, params.v_stop, params.v_step)
    if params.settle_time_s < 0:
        raise ValueError("Settle time must be non-negative")
    if params.compliance_tolerance < 0 or params.compliance_tolerance >= 1:
        raise ValueError("Compliance tolerance must be in the range [0, 1)")

    limits.validate_current(channel, params.current_limit)
    for voltage in values:
        limits.validate_setting(channel, voltage, params.current_limit)

    return SweepParameters(
        channel=channel,
        v_start=params.v_start,
        v_stop=params.v_stop,
        v_step=params.v_step,
        current_limit=params.current_limit,
        settle_time_s=params.settle_time_s,
        compliance_tolerance=params.compliance_tolerance,
        notes=params.notes,
    )


def run_dc_sweep(
    supply: object,
    params: SweepParameters,
    limits: SafetyLimits | None = None,
    stop_requested: Callable[[], bool] | None = None,
    on_point: Callable[[SweepPoint], None] | None = None,
) -> list[SweepPoint]:
    limits = limits or SafetyLimits()
    params = validate_sweep(params, limits)
    values = generate_sweep_values(params.v_start, params.v_stop, params.v_step)
    stop_requested = stop_requested or (lambda: False)

    points: list[SweepPoint] = []
    t0 = time.monotonic()
    supply.set_current_limit(params.channel, params.current_limit)
    if values:
        supply.set_voltage(params.channel, values[0])
    supply.output_on(params.channel)

    for voltage in values:
        if stop_requested():
            break

        supply.set_voltage(params.channel, voltage)
        if params.settle_time_s:
            time.sleep(params.settle_time_s)

        measured_voltage = float(supply.measure_voltage(params.channel))
        measured_current = float(supply.measure_current(params.channel))
        power = measured_voltage * measured_current
        compliance = is_in_compliance(
            measured_current,
            params.current_limit,
            params.compliance_tolerance,
        )
        point = SweepPoint(
            timestamp_iso=datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
            t_s=time.monotonic() - t0,
            channel=params.channel,
            Vset_V=voltage,
            Vmeas_V=measured_voltage,
            Imeas_A=measured_current,
            P_W=power,
            compliance_flag=compliance,
            notes=params.notes,
        )
        points.append(point)
        if on_point is not None:
            on_point(point)

        if compliance:
            break

    return points
