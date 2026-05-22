from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass, field
from typing import Any

from src.utils.units import normalize_channel


SWEEP_TYPES = {"linear", "decade", "octave", "list"}
SOURCE_MODES = {"voltage", "current"}
MAX_SWEEP_VALUES = 100_000
MAX_NESTED_POINTS = 1_000_000


@dataclass(frozen=True)
class SweepSource:
    name: str
    channel: str
    mode: str = "voltage"
    sweep_type: str = "linear"
    start: float = 0.0
    stop: float = 1.0
    increment: float | None = 0.1
    points_per_decade: int | None = None
    points_per_octave: int | None = None
    values_list: list[float] | None = field(default_factory=list)
    enabled: bool = True


def parse_values_list(text: str) -> list[float]:
    tokens = [token for token in re.split(r"[\s,]+", text.strip()) if token]
    values: list[float] = []
    for token in tokens:
        try:
            value = float(token)
        except ValueError as exc:
            raise ValueError(f"Invalid list sweep value: {token!r}") from exc
        _validate_finite(value, "List sweep value")
        values.append(value)
    if not values:
        raise ValueError("List sweep requires at least one value")
    return values


def enabled_sources(sources: list[SweepSource]) -> list[SweepSource]:
    return [source for source in sources if source.enabled]


def normalize_source(source: SweepSource) -> SweepSource:
    name = source.name.strip()
    if not name:
        raise ValueError("Enabled sweep sources require a source name")

    channel = normalize_channel(source.channel)
    mode = source.mode.strip().lower()
    sweep_type = source.sweep_type.strip().lower()
    if mode not in SOURCE_MODES:
        raise ValueError(f"Unsupported source mode for {name}: {source.mode!r}")
    if mode == "current":
        raise ValueError("Current sweep is reserved for future hardware support")
    if sweep_type not in SWEEP_TYPES:
        raise ValueError(f"Unsupported sweep type for {name}: {source.sweep_type!r}")

    return SweepSource(
        name=name,
        channel=channel,
        mode=mode,
        sweep_type=sweep_type,
        start=float(source.start),
        stop=float(source.stop),
        increment=None if source.increment is None else float(source.increment),
        points_per_decade=source.points_per_decade,
        points_per_octave=source.points_per_octave,
        values_list=list(source.values_list or []),
        enabled=source.enabled,
    )


def generate_sweep_values(source: SweepSource) -> list[float]:
    source = normalize_source(source)
    if source.sweep_type == "linear":
        return _linear_values(source.start, source.stop, source.increment)
    if source.sweep_type == "decade":
        points_per_decade = _positive_int(
            source.points_per_decade,
            f"{source.name} points per decade",
        )
        return _log_values(source.start, source.stop, points_per_decade, base=10.0)
    if source.sweep_type == "octave":
        points_per_octave = _positive_int(
            source.points_per_octave if source.points_per_octave is not None else source.points_per_decade,
            f"{source.name} points per octave",
        )
        return _log_values(source.start, source.stop, points_per_octave, base=2.0)
    if source.sweep_type == "list":
        values = [_round_value(float(value)) for value in source.values_list or []]
        if not values:
            raise ValueError(f"{source.name} list sweep requires at least one value")
        for value in values:
            _validate_finite(value, f"{source.name} list sweep value")
        if len(values) > MAX_SWEEP_VALUES:
            raise ValueError(f"{source.name} list sweep has too many values")
        return values
    raise ValueError(f"Unsupported sweep type: {source.sweep_type!r}")


def generate_nested_sweep_points(sources: list[SweepSource]) -> list[dict[str, float]]:
    active_sources = [normalize_source(source) for source in enabled_sources(sources)]
    if not active_sources:
        raise ValueError("At least one sweep source must be enabled")
    _validate_unique_names_and_channels(active_sources)

    value_lists = [generate_sweep_values(source) for source in active_sources]
    point_count = math.prod(len(values) for values in value_lists)
    if point_count > MAX_NESTED_POINTS:
        raise ValueError(f"Nested sweep would generate {point_count} points")

    points: list[dict[str, float]] = []
    reversed_sources = list(reversed(active_sources))
    reversed_values = list(reversed(value_lists))
    for reversed_combo in itertools.product(*reversed_values):
        values_by_name = {
            source.name: value
            for source, value in zip(reversed_sources, reversed_combo, strict=True)
        }
        points.append({source.name: values_by_name[source.name] for source in active_sources})
    return points


def generate_dc_directive(sources: list[SweepSource]) -> str:
    active_sources = [normalize_source(source) for source in enabled_sources(sources)]
    if not active_sources:
        return ".dc"
    _validate_unique_names_and_channels(active_sources)

    parts = [".dc"]
    for source in active_sources:
        parts.extend(_directive_parts_for_source(source))
    return " ".join(parts)


def source_values_by_name(sources: list[SweepSource]) -> dict[str, list[float]]:
    return {source.name: generate_sweep_values(source) for source in enabled_sources(sources)}


def sweep_source_from_dict(data: dict[str, Any]) -> SweepSource:
    return SweepSource(
        name=str(data.get("name", "")),
        channel=str(data.get("channel", "CH1")),
        mode=str(data.get("mode", "voltage")),
        sweep_type=str(data.get("sweep_type", "linear")),
        start=float(data.get("start", 0.0)),
        stop=float(data.get("stop", 1.0)),
        increment=data.get("increment", 0.1),
        points_per_decade=data.get("points_per_decade"),
        points_per_octave=data.get("points_per_octave"),
        values_list=[float(value) for value in data.get("values_list") or []],
        enabled=bool(data.get("enabled", True)),
    )


def _directive_parts_for_source(source: SweepSource) -> list[str]:
    if source.sweep_type == "linear":
        increment = source.increment
        if increment is None:
            raise ValueError(f"{source.name} linear sweep requires increment")
        return [
            source.name,
            _format_value(source.start),
            _format_value(source.stop),
            _format_value(increment),
        ]
    if source.sweep_type == "decade":
        return [
            "dec",
            source.name,
            _format_value(source.start),
            _format_value(source.stop),
            str(_positive_int(source.points_per_decade, f"{source.name} points per decade")),
        ]
    if source.sweep_type == "octave":
        points = _positive_int(
            source.points_per_octave if source.points_per_octave is not None else source.points_per_decade,
            f"{source.name} points per octave",
        )
        return ["oct", source.name, _format_value(source.start), _format_value(source.stop), str(points)]
    if source.sweep_type == "list":
        values = generate_sweep_values(source)
        return [source.name, "list", *[_format_value(value) for value in values]]
    raise ValueError(f"Unsupported sweep type: {source.sweep_type!r}")


def _linear_values(start: float, stop: float, increment: float | None) -> list[float]:
    _validate_finite(start, "Linear start value")
    _validate_finite(stop, "Linear stop value")
    if increment is None:
        raise ValueError("Linear sweep requires increment")
    _validate_finite(increment, "Linear increment")
    if increment == 0:
        raise ValueError("Linear sweep increment must be non-zero")
    if start == stop:
        return [_round_value(start)]

    if start < stop and increment < 0:
        raise ValueError("Linear sweep increment must be positive for ascending sweeps")
    if start > stop and increment > 0:
        raise ValueError("Linear sweep increment must be negative for descending sweeps")

    direction = 1.0 if stop >= start else -1.0
    epsilon = max(abs(increment) * 1e-9, 1e-12)
    values: list[float] = []
    value = float(start)
    while direction * (value - stop) <= epsilon:
        values.append(_round_value(value))
        value += increment
        if len(values) > MAX_SWEEP_VALUES:
            raise ValueError("Sweep would generate too many values")

    if not values:
        values.append(_round_value(start))
    if abs(values[-1] - stop) > epsilon:
        values.append(_round_value(stop))
    return values


def _log_values(start: float, stop: float, points: int, *, base: float) -> list[float]:
    _validate_finite(start, "Log sweep start value")
    _validate_finite(stop, "Log sweep stop value")
    if start <= 0:
        raise ValueError("Logarithmic sweep start must be greater than zero")
    if stop <= start:
        raise ValueError("Logarithmic sweep stop must be greater than start")

    factor = base ** (1.0 / points)
    epsilon = max(abs(stop) * 1e-9, 1e-15)
    values: list[float] = []
    value = float(start)
    while value <= stop + epsilon:
        values.append(_round_value(value))
        value *= factor
        if len(values) > MAX_SWEEP_VALUES:
            raise ValueError("Sweep would generate too many values")

    if abs(values[-1] - stop) > epsilon:
        values.append(_round_value(stop))
    return values


def _positive_int(value: int | None, name: str) -> int:
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        points = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if points <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return points


def _validate_unique_names_and_channels(sources: list[SweepSource]) -> None:
    names = [source.name for source in sources]
    if len(set(names)) != len(names):
        raise ValueError("Sweep source names must be unique")
    channels = [source.channel for source in sources]
    if len(set(channels)) != len(channels):
        raise ValueError("A physical channel cannot be assigned to more than one swept source")


def _validate_finite(value: float, label: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")


def _round_value(value: float) -> float:
    return round(float(value), 12)


def _format_value(value: float) -> str:
    return f"{float(value):.12g}"
