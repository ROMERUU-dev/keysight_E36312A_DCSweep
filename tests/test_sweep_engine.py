from __future__ import annotations

import json
import time

from src.instruments.keysight_supply import KeysightSupply
from src.instruments.visa_manager import MOCK_RESOURCE
from src.measurements.ltspice_dc_sweep import SweepSource
from src.measurements.sweep_engine import (
    FixedSource,
    SweepRunConfig,
    run_ltspice_dc_sweep,
    validate_sweep_run_config,
)


def test_engine_three_source_order_and_exports(tmp_path) -> None:
    supply = KeysightSupply(MOCK_RESOURCE, mock=True)
    supply.connect()
    try:
        config = SweepRunConfig(
            sweep_name="three_source_order",
            sources=[
                SweepSource(name="VDS", channel="CH1", start=0, stop=1, increment=1),
                SweepSource(name="VGS", channel="CH2", start=0, stop=2, increment=2),
                SweepSource(name="VBS", channel="CH3", start=0, stop=3, increment=3),
            ],
            fixed_sources=[
                FixedSource(channel="CH1", mode="swept_source", current_limit=0.1),
                FixedSource(channel="CH2", mode="swept_source", current_limit=0.1),
                FixedSource(channel="CH3", mode="swept_source", current_limit=0.1),
            ],
            settle_time_s=0,
            auto_export=True,
            output_root=str(tmp_path),
            mock_model="resistor",
        )
        result = run_ltspice_dc_sweep(supply, config)

        assert [(p.source1_value, p.source2_value, p.source3_value) for p in result.points] == [
            (0, 0, 0),
            (1, 0, 0),
            (0, 2, 0),
            (1, 2, 0),
            (0, 0, 3),
            (1, 0, 3),
            (0, 2, 3),
            (1, 2, 3),
        ]
        assert result.output_dir is not None
        run_dir = tmp_path / result.output_dir.split("/")[-1]
        assert (run_dir / "data.csv").exists()
        assert (run_dir / "metadata.json").exists()
        assert (run_dir / "sweep_config.json").exists()
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["dc_directive"] == ".dc VDS 0 1 1 VGS 0 2 2 VBS 0 3 3"
        assert all(not supply.query_output_state(channel) for channel in ("CH1", "CH2", "CH3"))
    finally:
        supply.safe_shutdown(close=True)


def test_stop_request_interrupts_settle_without_waiting_full_time(tmp_path) -> None:
    supply = KeysightSupply(MOCK_RESOURCE, mock=True)
    supply.connect()
    calls = 0

    def stop_requested() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 3

    try:
        config = SweepRunConfig(
            sweep_name="stop_during_settle",
            sources=[SweepSource(name="VIN", channel="CH1", start=0, stop=5, increment=1)],
            fixed_sources=[FixedSource(channel="CH1", mode="swept_source", current_limit=0.1)],
            settle_time_s=1.0,
            auto_export=False,
            output_root=str(tmp_path),
        )
        started = time.monotonic()
        result = run_ltspice_dc_sweep(supply, config, stop_requested=stop_requested)

        assert time.monotonic() - started < 0.5
        assert result.points == []
        assert "Stop requested during settle" in "\n".join(result.log_lines)
    finally:
        supply.safe_shutdown(close=True)


def test_mock_nmos_generates_id_vds_family_by_vgs(tmp_path) -> None:
    supply = KeysightSupply(MOCK_RESOURCE, mock=True)
    supply.connect()
    try:
        config = SweepRunConfig(
            sweep_name="nmos_family",
            sources=[
                SweepSource(name="VDS", channel="CH1", start=0, stop=2, increment=1),
                SweepSource(name="VGS", channel="CH2", start=1.5, stop=2.5, increment=1),
            ],
            fixed_sources=[
                FixedSource(channel="CH1", mode="swept_source", current_limit=0.1),
                FixedSource(channel="CH2", mode="swept_source", current_limit=0.01),
            ],
            settle_time_s=0,
            auto_export=False,
            output_root=str(tmp_path),
            mock_model="nmos",
            group_by="source2_value",
        )
        result = run_ltspice_dc_sweep(supply, config)

        vgs_15 = [point for point in result.points if point.source2_value == 1.5]
        vgs_25 = [point for point in result.points if point.source2_value == 2.5]
        assert [point.source1_value for point in vgs_15] == [0, 1, 2]
        assert [point.source1_value for point in vgs_25] == [0, 1, 2]
        assert vgs_25[1].CH1_Imeas > vgs_15[1].CH1_Imeas
        assert vgs_25[2].CH1_Imeas > vgs_15[2].CH1_Imeas
    finally:
        supply.safe_shutdown(close=True)


def test_validate_rejects_source_slot_gap() -> None:
    config = SweepRunConfig(
        sources=[
            SweepSource(name="VDS", channel="CH1", enabled=True),
            SweepSource(name="VGS", channel="CH2", enabled=False),
            SweepSource(name="VBS", channel="CH3", enabled=True),
        ]
    )
    try:
        validate_sweep_run_config(config)
    except ValueError as exc:
        assert "source 3" in str(exc)
    else:
        raise AssertionError("Expected source slot gap validation to fail")
