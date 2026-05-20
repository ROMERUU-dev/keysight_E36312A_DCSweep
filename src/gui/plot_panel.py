from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

import pyqtgraph as pg

from src.measurements.dc_sweep import SweepPoint


class PlotPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "Voltage", units="V")
        self.plot.setLabel("left", "Current", units="A")
        self.curve = self.plot.plot([], [], pen=pg.mkPen("#1f77b4", width=2), symbol="o")
        layout.addWidget(self.plot)
        self._x: list[float] = []
        self._y: list[float] = []

    def clear(self) -> None:
        self._x.clear()
        self._y.clear()
        self.curve.setData([], [])

    def append_point(self, point: SweepPoint | dict[str, object]) -> None:
        if isinstance(point, dict):
            voltage = float(point["Vmeas_V"])
            current = float(point["Imeas_A"])
        else:
            voltage = point.Vmeas_V
            current = point.Imeas_A
        self._x.append(voltage)
        self._y.append(current)
        self.curve.setData(self._x, self._y)
