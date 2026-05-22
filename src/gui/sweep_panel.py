from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.measurements.dc_sweep import SweepParameters
from src.utils.units import CHANNELS


class SweepPanel(QWidget):
    start_requested = Signal(object)
    stop_requested = Signal()
    export_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(CHANNELS)

        self.v_start = self._spin(-25.0, 25.0, 0.0, " V")
        self.v_stop = self._spin(-25.0, 25.0, 1.0, " V")
        self.v_step = self._spin(0.0001, 25.0, 0.1, " V")
        self.current_limit = self._spin(0.000001, 5.0, 0.1, " A", decimals=6)
        self.settle_time = self._spin(0.0, 60.0, 0.1, " s", decimals=3)
        self.compliance_tolerance = self._spin(0.0, 0.95, 0.02, "", decimals=3)

        form = QFormLayout()
        form.addRow("Channel", self.channel_combo)
        form.addRow("V start", self.v_start)
        form.addRow("V stop", self.v_stop)
        form.addRow("V step", self.v_step)
        form.addRow("I limit", self.current_limit)
        form.addRow("Settle time", self.settle_time)
        form.addRow("Compliance tolerance", self.compliance_tolerance)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start Sweep")
        self.stop_button = QPushButton("STOP")
        self.export_button = QPushButton("Export CSV")
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.export_button)

        self.status_label = QLabel("Idle")
        self.status_label.setWordWrap(True)
        self.csv_label = QLabel("CSV: -")
        self.csv_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        layout.addWidget(self.csv_label)
        layout.addStretch(1)

        self.start_button.clicked.connect(self._emit_start)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.export_button.clicked.connect(self.export_requested.emit)
        self.set_running(False)

    def parameters(self) -> SweepParameters:
        return SweepParameters(
            channel=self.channel_combo.currentText(),
            v_start=self.v_start.value(),
            v_stop=self.v_stop.value(),
            v_step=self.v_step.value(),
            current_limit=self.current_limit.value(),
            settle_time_s=self.settle_time.value(),
            compliance_tolerance=self.compliance_tolerance.value(),
        )

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.channel_combo.setEnabled(not running)
        self.export_button.setEnabled(not running)

    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def set_csv_path(self, path: str) -> None:
        self.csv_label.setText(f"CSV: {path}")

    def _emit_start(self) -> None:
        self.start_requested.emit(self.parameters())

    @staticmethod
    def _spin(
        minimum: float,
        maximum: float,
        value: float,
        suffix: str,
        *,
        decimals: int = 4,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(0.1)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin
