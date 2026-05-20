import pandas as pd

from src.measurements.data_export import SWEEP_COLUMNS, export_sweep_csv
from src.measurements.dc_sweep import SweepPoint


def test_export_sweep_csv_writes_expected_columns(tmp_path) -> None:
    points = [
        SweepPoint(
            timestamp_iso="2026-05-20T12:00:00-07:00",
            t_s=0.0,
            channel="CH1",
            Vset_V=1.0,
            Vmeas_V=0.999,
            Imeas_A=0.001,
            P_W=0.000999,
            compliance_flag=False,
            notes="test",
        )
    ]
    path = export_sweep_csv(points, tmp_path / "sweep.csv")
    dataframe = pd.read_csv(path)
    assert list(dataframe.columns) == SWEEP_COLUMNS
    assert dataframe.loc[0, "channel"] == "CH1"
    assert dataframe.loc[0, "Vset_V"] == 1.0
