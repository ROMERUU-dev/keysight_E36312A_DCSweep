from __future__ import annotations

import csv
import json
import math
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.measurements.dc_sweep import is_in_compliance
from src.measurements.ltspice_dc_sweep import (
    SweepSource,
    enabled_sources,
    generate_dc_directive,
    generate_nested_sweep_points,
    generate_sweep_values,
    normalize_source,
    sweep_source_from_dict,
)
from src.measurements.safety import SafetyLimits
from src.utils.units import CHANNELS, normalize_channel


FIXED_SOURCE_MODES = {"off", "fixed_voltage", "swept_source"}
DEFAULT_CURRENT_LIMIT_A = 0.1


@dataclass(frozen=True)
class FixedSource:
    channel: str
    mode: str = "off"
    voltage: float = 0.0
    current_limit: float = DEFAULT_CURRENT_LIMIT_A


@dataclass(frozen=True)
class SweepRunConfig:
    sweep_name: str = "ltspice_dc_sweep"
    sources: list[SweepSource] = field(default_factory=list)
    fixed_sources: list[FixedSource] = field(default_factory=list)
    settle_time_s: float = 0.1
    compliance_tolerance: float = 0.02
    stop_on_compliance: bool = True
    ramp_down_enabled: bool = True
    output_off_when_done: bool = True
    auto_export: bool = True
    output_root: str = "runs"
    notes: str = ""
    mock_model: str = "resistor"
    x_axis: str = "source1_value"
    y_axis: str = "CH1_Imeas"
    group_by: str = "source2_value"
    clear_plot_before_run: bool = True
    hold_previous_traces: bool = False
    autoscale: bool = True
    log_x: bool = False
    log_y: bool = False


@dataclass(frozen=True)
class SweepMeasurementPoint:
    timestamp_iso: str
    t_s: float
    sweep_index: int
    source1_name: str | None
    source1_value: float | None
    source2_name: str | None
    source2_value: float | None
    source3_name: str | None
    source3_value: float | None
    CH1_Vset: float
    CH1_Vmeas: float
    CH1_Imeas: float
    CH1_P: float
    CH2_Vset: float
    CH2_Vmeas: float
    CH2_Imeas: float
    CH2_P: float
    CH3_Vset: float
    CH3_Vmeas: float
    CH3_Imeas: float
    CH3_P: float
    compliance_flag: bool
    compliance_channel: str
    notes: str = ""


@dataclass(frozen=True)
class SweepRunResult:
    points: list[SweepMeasurementPoint]
    output_dir: str | None = None
    log_lines: list[str] = field(default_factory=list)


LTSPICE_SWEEP_COLUMNS = [
    "timestamp_iso",
    "t_s",
    "sweep_index",
    "source1_name",
    "source1_value",
    "source2_name",
    "source2_value",
    "source3_name",
    "source3_value",
    "CH1_Vset",
    "CH1_Vmeas",
    "CH1_Imeas",
    "CH1_P",
    "CH2_Vset",
    "CH2_Vmeas",
    "CH2_Imeas",
    "CH2_P",
    "CH3_Vset",
    "CH3_Vmeas",
    "CH3_Imeas",
    "CH3_P",
    "compliance_flag",
    "compliance_channel",
    "notes",
]


def default_fixed_sources(current_limits: dict[str, float] | None = None) -> list[FixedSource]:
    current_limits = current_limits or {}
    return [
        FixedSource(channel=channel, mode="off", current_limit=current_limits.get(channel, DEFAULT_CURRENT_LIMIT_A))
        for channel in CHANNELS
    ]


def fixed_sources_by_channel(fixed_sources: list[FixedSource]) -> dict[str, FixedSource]:
    result = {source.channel: source for source in default_fixed_sources()}
    seen: set[str] = set()
    for source in fixed_sources:
        normalized = normalize_fixed_source(source)
        if normalized.channel in seen:
            raise ValueError(f"Fixed source for {normalized.channel} is defined more than once")
        seen.add(normalized.channel)
        result[normalized.channel] = normalized
    return result


def normalize_fixed_source(source: FixedSource) -> FixedSource:
    channel = normalize_channel(source.channel)
    mode = source.mode.strip().lower()
    if mode not in FIXED_SOURCE_MODES:
        raise ValueError(f"Unsupported fixed source mode for {channel}: {source.mode!r}")
    voltage = float(source.voltage)
    current_limit = float(source.current_limit)
    _validate_finite(voltage, f"{channel} fixed voltage")
    _validate_finite(current_limit, f"{channel} current limit")
    return FixedSource(channel=channel, mode=mode, voltage=voltage, current_limit=current_limit)


def validate_sweep_run_config(
    config: SweepRunConfig,
    limits: SafetyLimits | None = None,
) -> SweepRunConfig:
    limits = limits or SafetyLimits()
    _validate_contiguous_source_slots(config.sources)
    active_sources = [normalize_source(source) for source in enabled_sources(config.sources)]
    if not active_sources:
        raise ValueError("Enable at least one LTspice sweep source")
    if len(active_sources) > 3:
        raise ValueError("Only 1st, 2nd and 3rd sources are supported")

    source_names = [source.name for source in active_sources]
    if len(set(source_names)) != len(source_names):
        raise ValueError("Sweep source names must be unique")
    source_channels = [source.channel for source in active_sources]
    if len(set(source_channels)) != len(source_channels):
        raise ValueError("A channel cannot be swept by more than one source")

    fixed_by_channel = fixed_sources_by_channel(config.fixed_sources)
    for channel, fixed_source in fixed_by_channel.items():
        limits.validate_current(channel, fixed_source.current_limit)
        if fixed_source.mode == "fixed_voltage":
            if channel in source_channels:
                raise ValueError(f"{channel} cannot be fixed and swept at the same time")
            limits.validate_setting(channel, fixed_source.voltage, fixed_source.current_limit)
        if fixed_source.mode == "swept_source" and channel not in source_channels:
            raise ValueError(f"{channel} is marked as swept but no source uses it")

    for source in active_sources:
        current_limit = fixed_by_channel[source.channel].current_limit
        for value in generate_sweep_values(source):
            limits.validate_setting(source.channel, value, current_limit)

    _validate_finite(config.settle_time_s, "Settle time")
    _validate_finite(config.compliance_tolerance, "Compliance tolerance")
    if config.settle_time_s < 0:
        raise ValueError("Settle time must be non-negative")
    if not 0 <= config.compliance_tolerance < 1:
        raise ValueError("Compliance tolerance must be in the range [0, 1)")

    normalized_fixed_sources: list[FixedSource] = []
    for channel in CHANNELS:
        fixed_source = fixed_by_channel[channel]
        if channel in source_channels and fixed_source.mode == "off":
            fixed_source = FixedSource(
                channel=channel,
                mode="swept_source",
                voltage=fixed_source.voltage,
                current_limit=fixed_source.current_limit,
            )
        normalized_fixed_sources.append(fixed_source)

    return SweepRunConfig(
        sweep_name=config.sweep_name.strip() or "ltspice_dc_sweep",
        sources=active_sources,
        fixed_sources=normalized_fixed_sources,
        settle_time_s=config.settle_time_s,
        compliance_tolerance=config.compliance_tolerance,
        stop_on_compliance=config.stop_on_compliance,
        ramp_down_enabled=config.ramp_down_enabled,
        output_off_when_done=config.output_off_when_done,
        auto_export=config.auto_export,
        output_root=config.output_root,
        notes=config.notes,
        mock_model=config.mock_model,
        x_axis=config.x_axis,
        y_axis=config.y_axis,
        group_by=config.group_by,
        clear_plot_before_run=config.clear_plot_before_run,
        hold_previous_traces=config.hold_previous_traces,
        autoscale=config.autoscale,
        log_x=config.log_x,
        log_y=config.log_y,
    )


def run_ltspice_dc_sweep(
    supply: object,
    config: SweepRunConfig,
    limits: SafetyLimits | None = None,
    *,
    stop_requested: Callable[[], bool] | None = None,
    on_point: Callable[[SweepMeasurementPoint], None] | None = None,
) -> SweepRunResult:
    limits = limits or SafetyLimits()
    config = validate_sweep_run_config(config, limits)
    stop_requested = stop_requested or (lambda: False)
    active_sources = config.sources
    fixed_by_channel = fixed_sources_by_channel(config.fixed_sources)
    sweep_points = generate_nested_sweep_points(active_sources)
    source_channels = {source.name: source.channel for source in active_sources}
    active_channels = {
        source.channel for source in active_sources
    } | {
        fixed.channel for fixed in fixed_by_channel.values() if fixed.mode == "fixed_voltage"
    }
    current_limits = {channel: fixed_by_channel[channel].current_limit for channel in CHANNELS}
    fixed_targets = {
        fixed.channel: fixed.voltage
        for fixed in fixed_by_channel.values()
        if fixed.mode == "fixed_voltage"
    }
    target_by_channel = {channel: 0.0 for channel in CHANNELS}
    target_by_channel.update(fixed_targets)
    points: list[SweepMeasurementPoint] = []
    log_lines: list[str] = []
    t0 = time.monotonic()
    started_at = datetime.now(timezone.utc).astimezone()
    instrument_idn = ""

    if hasattr(supply, "set_mock_model"):
        try:
            supply.set_mock_model(config.mock_model)
        except Exception as exc:  # pragma: no cover - defensive for third-party drivers
            log_lines.append(f"Could not set mock model {config.mock_model!r}: {exc}")

    try:
        instrument_idn = str(supply.identify())
    except Exception as exc:
        instrument_idn = f"IDN unavailable: {exc}"

    supply.output_all_off()
    for channel in active_channels:
        supply.set_current_limit(channel, current_limits[channel])

    if sweep_points:
        for source in active_sources:
            target_by_channel[source.channel] = float(sweep_points[0][source.name])

    for channel, voltage in target_by_channel.items():
        if channel in active_channels:
            supply.set_voltage(channel, voltage)
    for channel in active_channels:
        supply.output_on(channel)

    for index, source_values in enumerate(sweep_points):
        if stop_requested():
            log_lines.append(f"Stop requested before point {index}")
            break

        stop_before_measurement = False
        for source in active_sources:
            if stop_requested():
                log_lines.append(f"Stop requested while setting point {index}")
                stop_before_measurement = True
                break
            channel = source_channels[source.name]
            voltage = float(source_values[source.name])
            target_by_channel[channel] = voltage
            supply.set_voltage(channel, voltage)
        if stop_before_measurement:
            break

        if config.settle_time_s and not _wait_for_settle(config.settle_time_s, stop_requested):
            log_lines.append(f"Stop requested during settle before point {index} measurement")
            break

        measurements = _measure_channels(supply, active_channels, current_limits, target_by_channel, config)
        point = _make_point(
            index=index,
            t0=t0,
            sources=active_sources,
            source_values=source_values,
            target_by_channel=target_by_channel,
            measurements=measurements,
            notes=config.notes,
        )
        points.append(point)
        if on_point is not None:
            on_point(point)

        if point.compliance_flag:
            log_lines.append(
                f"Compliance at point {index} on {point.compliance_channel or 'unknown channel'}"
            )
            if config.stop_on_compliance:
                break

    if config.ramp_down_enabled:
        _ramp_down_active_channels(supply, active_channels, log_lines)
    if config.output_off_when_done:
        _output_off_all_channels(supply, log_lines)

    output_dir: str | None = None
    if config.auto_export:
        output_dir = str(
            export_ltspice_sweep_run(
                points,
                config,
                instrument_idn=instrument_idn,
                visa_resource=str(getattr(supply, "resource_name", "")),
                started_at=started_at,
                limits=limits,
                log_lines=log_lines,
            )
        )

    return SweepRunResult(points=points, output_dir=output_dir, log_lines=log_lines)


def export_ltspice_sweep_run(
    points: list[SweepMeasurementPoint],
    config: SweepRunConfig,
    *,
    instrument_idn: str,
    visa_resource: str,
    started_at: datetime,
    limits: SafetyLimits,
    log_lines: list[str] | None = None,
) -> Path:
    run_dir = _run_directory(Path(config.output_root), started_at, config.sweep_name)
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_points_csv(points, run_dir / "data.csv")
    config_dict = sweep_run_config_to_dict(config)
    (run_dir / "sweep_config.json").write_text(
        json.dumps(config_dict, indent=2),
        encoding="utf-8",
    )
    metadata = {
        "instrument_idn": instrument_idn,
        "visa_resource": visa_resource,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "dc_directive": generate_dc_directive(config.sources),
        "sources": [asdict(source) for source in config.sources],
        "fixed_sources": [asdict(source) for source in config.fixed_sources],
        "safety_limits": asdict(limits),
        "settle_time_s": config.settle_time_s,
        "program_version": "unknown",
        "notes": config.notes,
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (run_dir / "log.txt").write_text("\n".join(log_lines or []) + "\n", encoding="utf-8")
    return run_dir


def sweep_run_config_to_dict(config: SweepRunConfig) -> dict[str, Any]:
    return {
        "sweep_name": config.sweep_name,
        "sources": [asdict(source) for source in config.sources],
        "fixed_sources": [asdict(source) for source in config.fixed_sources],
        "settle_time_s": config.settle_time_s,
        "compliance_tolerance": config.compliance_tolerance,
        "stop_on_compliance": config.stop_on_compliance,
        "ramp_down_enabled": config.ramp_down_enabled,
        "output_off_when_done": config.output_off_when_done,
        "auto_export": config.auto_export,
        "output_root": config.output_root,
        "notes": config.notes,
        "mock_model": config.mock_model,
        "x_axis": config.x_axis,
        "y_axis": config.y_axis,
        "group_by": config.group_by,
        "clear_plot_before_run": config.clear_plot_before_run,
        "hold_previous_traces": config.hold_previous_traces,
        "autoscale": config.autoscale,
        "log_x": config.log_x,
        "log_y": config.log_y,
    }


def sweep_run_config_from_dict(data: dict[str, Any]) -> SweepRunConfig:
    return SweepRunConfig(
        sweep_name=str(data.get("sweep_name", "ltspice_dc_sweep")),
        sources=[sweep_source_from_dict(source) for source in data.get("sources", [])],
        fixed_sources=[
            FixedSource(
                channel=str(source.get("channel", "CH1")),
                mode=str(source.get("mode", "off")),
                voltage=float(source.get("voltage", 0.0)),
                current_limit=float(source.get("current_limit", DEFAULT_CURRENT_LIMIT_A)),
            )
            for source in data.get("fixed_sources", [])
        ],
        settle_time_s=float(data.get("settle_time_s", 0.1)),
        compliance_tolerance=float(data.get("compliance_tolerance", 0.02)),
        stop_on_compliance=bool(data.get("stop_on_compliance", True)),
        ramp_down_enabled=bool(data.get("ramp_down_enabled", True)),
        output_off_when_done=bool(data.get("output_off_when_done", True)),
        auto_export=bool(data.get("auto_export", True)),
        output_root=str(data.get("output_root", "runs")),
        notes=str(data.get("notes", "")),
        mock_model=str(data.get("mock_model", "resistor")),
        x_axis=str(data.get("x_axis", "source1_value")),
        y_axis=str(data.get("y_axis", "CH1_Imeas")),
        group_by=str(data.get("group_by", "source2_value")),
        clear_plot_before_run=bool(data.get("clear_plot_before_run", True)),
        hold_previous_traces=bool(data.get("hold_previous_traces", False)),
        autoscale=bool(data.get("autoscale", True)),
        log_x=bool(data.get("log_x", False)),
        log_y=bool(data.get("log_y", False)),
    )


def preset_sweep_configs() -> dict[str, SweepRunConfig]:
    return {
        "Single Channel I-V": SweepRunConfig(
            sweep_name="single_channel_iv",
            sources=[SweepSource(name="VIN", channel="CH1", start=0, stop=5, increment=0.1)],
            fixed_sources=_fixed_for_swept({"CH1": 0.1}),
            y_axis="CH1_Imeas",
        ),
        "Diode I-V": SweepRunConfig(
            sweep_name="diode_iv",
            sources=[SweepSource(name="VDIODE", channel="CH1", start=0, stop=1, increment=0.01)],
            fixed_sources=_fixed_for_swept({"CH1": 0.01}),
            mock_model="diode",
            y_axis="CH1_Imeas",
            notes="Suggested current limit: 5 mA to 10 mA.",
        ),
        "NMOS Output Curves": SweepRunConfig(
            sweep_name="nmos_output_curves",
            sources=[
                SweepSource(name="VDS", channel="CH1", start=0, stop=5, increment=0.05),
                SweepSource(name="VGS", channel="CH2", start=0, stop=3.3, increment=0.1),
            ],
            fixed_sources=_fixed_for_swept({"CH1": 0.1, "CH2": 0.01}),
            mock_model="nmos",
            x_axis="source1_value",
            y_axis="CH1_Imeas",
            group_by="source2_value",
            notes="ID is measured as CH1 current. IG is measured as CH2 current.",
        ),
        "NMOS Transfer Curve": SweepRunConfig(
            sweep_name="nmos_transfer_curve",
            sources=[SweepSource(name="VGS", channel="CH2", start=0, stop=3.3, increment=0.01)],
            fixed_sources=[
                FixedSource(channel="CH1", mode="fixed_voltage", voltage=5.0, current_limit=0.1),
                FixedSource(channel="CH2", mode="swept_source", current_limit=0.01),
                FixedSource(channel="CH3", mode="off", current_limit=0.1),
            ],
            mock_model="nmos",
            x_axis="source1_value",
            y_axis="CH1_Imeas",
            group_by="none",
            notes="VDS is fixed on CH1; VGS is swept on CH2.",
        ),
        "BJT Output Curves": SweepRunConfig(
            sweep_name="bjt_output_curves",
            sources=[
                SweepSource(name="VCE", channel="CH1", start=0, stop=5, increment=0.05),
                SweepSource(name="VBASE", channel="CH2", start=0.55, stop=0.75, increment=0.01),
            ],
            fixed_sources=_fixed_for_swept({"CH1": 0.1, "CH2": 0.01}),
            x_axis="source1_value",
            y_axis="CH1_Imeas",
            group_by="source2_value",
            notes="Use an external base resistor to control real base current.",
        ),
    }


def _fixed_for_swept(current_limits: dict[str, float]) -> list[FixedSource]:
    return [
        FixedSource(
            channel=channel,
            mode="swept_source" if channel in current_limits else "off",
            current_limit=current_limits.get(channel, DEFAULT_CURRENT_LIMIT_A),
        )
        for channel in CHANNELS
    ]


def _measure_channels(
    supply: object,
    active_channels: set[str],
    current_limits: dict[str, float],
    target_by_channel: dict[str, float],
    config: SweepRunConfig,
) -> dict[str, dict[str, float | bool]]:
    measurements: dict[str, dict[str, float | bool]] = {}
    for channel in CHANNELS:
        if channel not in active_channels:
            measurements[channel] = {
                "Vset": target_by_channel.get(channel, 0.0),
                "Vmeas": 0.0,
                "Imeas": 0.0,
                "P": 0.0,
                "compliance": False,
            }
            continue
        measured_voltage = float(supply.measure_voltage(channel))
        measured_current = float(supply.measure_current(channel))
        power = measured_voltage * measured_current
        compliance = is_in_compliance(
            measured_current,
            current_limits[channel],
            config.compliance_tolerance,
        )
        measurements[channel] = {
            "Vset": target_by_channel.get(channel, 0.0),
            "Vmeas": measured_voltage,
            "Imeas": measured_current,
            "P": power,
            "compliance": compliance,
        }
    return measurements


def _make_point(
    *,
    index: int,
    t0: float,
    sources: list[SweepSource],
    source_values: dict[str, float],
    target_by_channel: dict[str, float],
    measurements: dict[str, dict[str, float | bool]],
    notes: str,
) -> SweepMeasurementPoint:
    source_names: list[str | None] = [source.name for source in sources]
    source_values_ordered: list[float | None] = [source_values[source.name] for source in sources]
    while len(source_names) < 3:
        source_names.append(None)
        source_values_ordered.append(None)

    compliance_channels = [
        channel for channel in CHANNELS if bool(measurements[channel]["compliance"])
    ]
    return SweepMeasurementPoint(
        timestamp_iso=datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
        t_s=time.monotonic() - t0,
        sweep_index=index,
        source1_name=source_names[0],
        source1_value=source_values_ordered[0],
        source2_name=source_names[1],
        source2_value=source_values_ordered[1],
        source3_name=source_names[2],
        source3_value=source_values_ordered[2],
        CH1_Vset=float(measurements["CH1"]["Vset"]),
        CH1_Vmeas=float(measurements["CH1"]["Vmeas"]),
        CH1_Imeas=float(measurements["CH1"]["Imeas"]),
        CH1_P=float(measurements["CH1"]["P"]),
        CH2_Vset=float(measurements["CH2"]["Vset"]),
        CH2_Vmeas=float(measurements["CH2"]["Vmeas"]),
        CH2_Imeas=float(measurements["CH2"]["Imeas"]),
        CH2_P=float(measurements["CH2"]["P"]),
        CH3_Vset=float(measurements["CH3"]["Vset"]),
        CH3_Vmeas=float(measurements["CH3"]["Vmeas"]),
        CH3_Imeas=float(measurements["CH3"]["Imeas"]),
        CH3_P=float(measurements["CH3"]["P"]),
        compliance_flag=bool(compliance_channels),
        compliance_channel=";".join(compliance_channels),
        notes=notes,
    )


def _ramp_down_active_channels(supply: object, active_channels: set[str], log_lines: list[str]) -> None:
    for channel in sorted(active_channels):
        try:
            supply.ramp_to_zero_and_off(channel, step_v=0.2, delay_s=0.0)
        except Exception as exc:
            log_lines.append(f"Could not ramp down {channel}: {exc}")


def _output_off_active_channels(supply: object, active_channels: set[str], log_lines: list[str]) -> None:
    for channel in sorted(active_channels):
        try:
            supply.output_off(channel)
        except Exception as exc:
            log_lines.append(f"Could not turn off {channel}: {exc}")


def _output_off_all_channels(supply: object, log_lines: list[str]) -> None:
    try:
        supply.output_all_off()
        return
    except Exception as exc:
        log_lines.append(f"Could not turn all outputs off at once: {exc}")
    _output_off_active_channels(supply, set(CHANNELS), log_lines)


def _wait_for_settle(duration_s: float, stop_requested: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + duration_s
    while True:
        if stop_requested():
            return False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(remaining, 0.025))


def _write_points_csv(points: list[SweepMeasurementPoint], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LTSPICE_SWEEP_COLUMNS)
        writer.writeheader()
        for point in points:
            writer.writerow(asdict(point))


def _run_directory(root: Path, started_at: datetime, sweep_name: str) -> Path:
    stamp = started_at.strftime("%Y-%m-%d_%H-%M-%S")
    slug = _slugify(sweep_name)
    candidate = root / f"{stamp}_{slug}"
    suffix = 2
    while candidate.exists():
        candidate = root / f"{stamp}_{slug}_{suffix}"
        suffix += 1
    return candidate


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._")
    return slug or "ltspice_dc_sweep"


def _validate_contiguous_source_slots(sources: list[SweepSource]) -> None:
    seen_disabled = False
    for index, source in enumerate(sources[:3], start=1):
        if not source.enabled:
            seen_disabled = True
            continue
        if seen_disabled:
            raise ValueError(
                f"Enable source slots in LTspice order; source {index} cannot be enabled after a disabled earlier source"
            )


def _validate_finite(value: float, label: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
