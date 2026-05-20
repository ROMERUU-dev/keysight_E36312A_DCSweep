from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.utils.units import CHANNELS


class ManualControlPanel(QWidget):
    set_voltage_requested = Signal(str, float)
    set_current_requested = Signal(str, float)
    output_requested = Signal(str, bool)
    measure_requested = Signal(str)
    all_off_requested = Signal()
    ramp_zero_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.voltage_spins: dict[str, QDoubleSpinBox] = {}
        self.current_spins: dict[str, QDoubleSpinBox] = {}
        self.voltage_labels: dict[str, QLabel] = {}
        self.current_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        for channel in CHANNELS:
            layout.addWidget(self._build_channel_group(channel))

        bottom = QHBoxLayout()
        self.all_off_button = QPushButton("All OFF")
        self.ramp_zero_button = QPushButton("Ramp to 0 V and OFF")
        bottom.addWidget(self.all_off_button)
        bottom.addWidget(self.ramp_zero_button)
        layout.addLayout(bottom)
        layout.addStretch(1)

        self.all_off_button.clicked.connect(self.all_off_requested.emit)
        self.ramp_zero_button.clicked.connect(self.ramp_zero_requested.emit)

    def _build_channel_group(self, channel: str) -> QGroupBox:
        group = QGroupBox(channel)
        grid = QGridLayout(group)

        voltage_spin = QDoubleSpinBox()
        voltage_spin.setRange(0.0, 25.0)
        voltage_spin.setDecimals(4)
        voltage_spin.setSingleStep(0.1)
        voltage_spin.setSuffix(" V")

        current_spin = QDoubleSpinBox()
        current_spin.setRange(0.0, 5.0)
        current_spin.setDecimals(5)
        current_spin.setSingleStep(0.01)
        current_spin.setSuffix(" A")
        current_spin.setValue(0.1)

        set_voltage = QPushButton("Set V")
        set_current = QPushButton("Set I limit")
        output_on = QPushButton("ON")
        output_off = QPushButton("OFF")
        measure = QPushButton("Measure")

        v_label = QLabel("V: -")
        i_label = QLabel("I: -")

        grid.addWidget(QLabel("Voltage"), 0, 0)
        grid.addWidget(voltage_spin, 0, 1)
        grid.addWidget(set_voltage, 0, 2)
        grid.addWidget(QLabel("Current limit"), 1, 0)
        grid.addWidget(current_spin, 1, 1)
        grid.addWidget(set_current, 1, 2)
        grid.addWidget(output_on, 2, 0)
        grid.addWidget(output_off, 2, 1)
        grid.addWidget(measure, 2, 2)
        grid.addWidget(v_label, 3, 0, 1, 2)
        grid.addWidget(i_label, 3, 2)

        self.voltage_spins[channel] = voltage_spin
        self.current_spins[channel] = current_spin
        self.voltage_labels[channel] = v_label
        self.current_labels[channel] = i_label

        set_voltage.clicked.connect(
            lambda _checked=False, ch=channel: self.set_voltage_requested.emit(
                ch, self.voltage_spins[ch].value()
            )
        )
        set_current.clicked.connect(
            lambda _checked=False, ch=channel: self.set_current_requested.emit(
                ch, self.current_spins[ch].value()
            )
        )
        output_on.clicked.connect(
            lambda _checked=False, ch=channel: self.output_requested.emit(ch, True)
        )
        output_off.clicked.connect(
            lambda _checked=False, ch=channel: self.output_requested.emit(ch, False)
        )
        measure.clicked.connect(lambda _checked=False, ch=channel: self.measure_requested.emit(ch))

        return group

    def set_measurements(self, channel: str, voltage_v: float, current_a: float) -> None:
        self.voltage_labels[channel].setText(f"V: {voltage_v:.6g} V")
        self.current_labels[channel].setText(f"I: {current_a:.6g} A")

    def set_controls_enabled(self, enabled: bool) -> None:
        self.setEnabled(enabled)
