from src.instruments.keysight_supply import KeysightSupply
from src.instruments.visa_manager import MOCK_RESOURCE
from src.measurements.dc_sweep import SweepParameters, run_dc_sweep


def test_mock_identify_and_measure() -> None:
    supply = KeysightSupply(MOCK_RESOURCE, mock=True)
    supply.connect()
    try:
        assert "E36312A" in supply.identify()
        supply.set_current_limit("CH1", 0.1)
        supply.set_voltage("CH1", 1.0)
        supply.output_on("CH1")
        assert supply.query_current_limit("CH1") == 0.1
        assert supply.query_voltage_setpoint("CH1") == 1.0
        assert supply.query_output_state("CH1") is True
        assert supply.measure_voltage("CH1") == 1.0
        assert supply.measure_current("CH1") == 0.001
    finally:
        supply.safe_shutdown(close=True)


def test_mock_sweep_stops_on_compliance() -> None:
    supply = KeysightSupply(MOCK_RESOURCE, mock=True)
    supply.connect()
    try:
        params = SweepParameters(
            channel="CH1",
            v_start=0.0,
            v_stop=2.0,
            v_step=1.0,
            current_limit=0.001,
            settle_time_s=0.0,
            compliance_tolerance=0.0,
        )
        points = run_dc_sweep(supply, params)
        assert points[-1].compliance_flag is True
        assert points[-1].Imeas_A == 0.001
    finally:
        supply.safe_shutdown(close=True)
