from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.gui.plot_panel import PlotPanel
from src.measurements.sweep_engine import SweepMeasurementPoint, SweepRunConfig


def test_ltspice_plot_groups_curves_by_source2() -> None:
    app = QApplication.instance() or QApplication([])
    panel = PlotPanel()
    panel.configure_ltspice(
        SweepRunConfig(
            x_axis="source1_value",
            y_axis="CH1_Imeas",
            group_by="source2_value",
        )
    )

    panel.append_point(_point(vds=0, vgs=1.5, current=0.0))
    panel.append_point(_point(vds=1, vgs=1.5, current=0.0025))
    panel.append_point(_point(vds=0, vgs=2.5, current=0.0))
    panel.append_point(_point(vds=1, vgs=2.5, current=0.01))

    assert set(panel._curves) == {"VGS=1.5", "VGS=2.5"}
    assert panel._curve_data["VGS=1.5"] == ([0.0, 1.0], [0.0, 0.0025])
    assert panel._curve_data["VGS=2.5"] == ([0.0, 1.0], [0.0, 0.01])
    panel.deleteLater()
    app.processEvents()


def _point(*, vds: float, vgs: float, current: float) -> SweepMeasurementPoint:
    return SweepMeasurementPoint(
        timestamp_iso="2026-05-22T12:00:00-07:00",
        t_s=0.0,
        sweep_index=0,
        source1_name="VDS",
        source1_value=vds,
        source2_name="VGS",
        source2_value=vgs,
        source3_name=None,
        source3_value=None,
        CH1_Vset=vds,
        CH1_Vmeas=vds,
        CH1_Imeas=current,
        CH1_P=vds * current,
        CH2_Vset=vgs,
        CH2_Vmeas=vgs,
        CH2_Imeas=1e-9,
        CH2_P=vgs * 1e-9,
        CH3_Vset=0.0,
        CH3_Vmeas=0.0,
        CH3_Imeas=0.0,
        CH3_P=0.0,
        compliance_flag=False,
        compliance_channel="",
    )
