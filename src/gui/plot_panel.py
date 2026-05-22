from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QVBoxLayout, QWidget

import pyqtgraph as pg

from src.measurements.dc_sweep import SweepPoint
from src.measurements.sweep_engine import SweepMeasurementPoint, SweepRunConfig


class PlotPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "Voltage", units="V")
        self.plot.setLabel("left", "Current", units="A")
        self._ensure_legend()
        layout.addWidget(self.plot)
        self._colors = [
            "#1f77b4",
            "#d62728",
            "#2ca02c",
            "#ff7f0e",
            "#9467bd",
            "#17becf",
            "#8c564b",
            "#e377c2",
            "#7f7f7f",
            "#bcbd22",
        ]
        self._ltspice_config: SweepRunConfig | None = None
        self._curves: dict[str, Any] = {}
        self._curve_data: dict[str, tuple[list[float], list[float]]] = {}
        self._x: list[float] = []
        self._y: list[float] = []
        self.curve = self.plot.plot([], [], pen=pg.mkPen(self._colors[0], width=2), symbol="o")

    def clear(self) -> None:
        self.plot.clear()
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self._ensure_legend()
        self._curves.clear()
        self._curve_data.clear()
        self._x.clear()
        self._y.clear()
        self.curve = self.plot.plot([], [], pen=pg.mkPen(self._colors[0], width=2), symbol="o")

    def configure_ltspice(self, config: SweepRunConfig) -> None:
        self._ltspice_config = config
        if config.clear_plot_before_run and not config.hold_previous_traces:
            self.clear()
        else:
            self._curves.clear()
            self._curve_data.clear()
        self.plot.setLogMode(x=config.log_x, y=config.log_y)
        self.plot.setLabel("bottom", _axis_label(config.x_axis))
        self.plot.setLabel("left", _axis_label(config.y_axis))

    def save_png(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self.plot.grab().save(str(output))
        return output

    def append_point(self, point: SweepPoint | SweepMeasurementPoint | dict[str, object]) -> None:
        row = _point_to_dict(point)
        if "Vmeas_V" in row:
            self._append_simple(row)
        else:
            self._append_ltspice(row)

    def _append_simple(self, row: dict[str, Any]) -> None:
        voltage = float(row["Vmeas_V"])
        current = float(row["Imeas_A"])
        self._x.append(voltage)
        self._y.append(current)
        self.curve.setData(self._x, self._y)

    def _append_ltspice(self, row: dict[str, Any]) -> None:
        config = self._ltspice_config
        if config is None:
            x_key = "source1_value"
            y_key = "CH1_Imeas"
            group_key = "source2_value"
            autoscale = True
        else:
            x_key = config.x_axis
            y_key = config.y_axis
            group_key = config.group_by
            autoscale = config.autoscale

        x_value = row.get(x_key)
        y_value = row.get(y_key)
        if x_value is None or y_value is None:
            return
        group = _group_name(row, group_key)
        if group not in self._curves:
            color = self._colors[len(self._curves) % len(self._colors)]
            self._curves[group] = self.plot.plot(
                [],
                [],
                pen=pg.mkPen(color, width=2),
                symbol="o",
                symbolSize=5,
                name=group,
            )
            self._curve_data[group] = ([], [])

        x_data, y_data = self._curve_data[group]
        x_data.append(float(x_value))
        y_data.append(float(y_value))
        self._curves[group].setData(x_data, y_data)
        if autoscale:
            self.plot.enableAutoRange()

    def _ensure_legend(self) -> None:
        if self.plot.plotItem.legend is None:
            self.plot.addLegend(offset=(10, 10))


def _point_to_dict(point: SweepPoint | SweepMeasurementPoint | dict[str, object]) -> dict[str, Any]:
    if isinstance(point, dict):
        return dict(point)
    if is_dataclass(point):
        return asdict(point)
    return dict(point)


def _axis_label(key: str) -> str:
    labels = {
        "source1_value": "Source1 value",
        "source2_value": "Source2 value",
        "source3_value": "Source3 value",
        "t_s": "time",
        "CH1_Vmeas": "CH1 Vmeas",
        "CH2_Vmeas": "CH2 Vmeas",
        "CH3_Vmeas": "CH3 Vmeas",
        "CH1_Imeas": "CH1 Imeas",
        "CH2_Imeas": "CH2 Imeas",
        "CH3_Imeas": "CH3 Imeas",
        "CH1_P": "CH1 P",
        "CH2_P": "CH2 P",
        "CH3_P": "CH3 P",
    }
    return labels.get(key, key)


def _group_name(row: dict[str, Any], group_key: str) -> str:
    if group_key == "none":
        return "sweep"
    value = row.get(group_key)
    if value is None:
        return "sweep"
    if group_key == "source2_value":
        name = row.get("source2_name") or "Source2"
    elif group_key == "source3_value":
        name = row.get("source3_name") or "Source3"
    else:
        name = group_key
    return f"{name}={float(value):.6g}"
