from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

from src.measurements.safety import SafetyLimits


class SettingsPanel(QWidget):
    def __init__(self, limits: SafetyLimits) -> None:
        super().__init__()
        self.shutdown_on_close = QCheckBox("Apagar salidas al cerrar")
        self.shutdown_on_close.setChecked(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.shutdown_on_close)
        layout.addWidget(QLabel("Limites activos por canal:"))
        for channel in ("CH1", "CH2", "CH3"):
            layout.addWidget(
                QLabel(
                    f"{channel}: 0-{limits.max_voltage_by_channel[channel]:.6g} V, "
                    f"0-{limits.max_current_by_channel[channel]:.6g} A, "
                    f"{limits.max_power_by_channel[channel]:.6g} W max"
                )
            )
        layout.addStretch(1)

    def should_shutdown_on_close(self) -> bool:
        return self.shutdown_on_close.isChecked()
