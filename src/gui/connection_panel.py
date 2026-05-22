from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ConnectionPanel(QWidget):
    connect_requested = Signal(str)
    disconnect_requested = Signal()
    refresh_requested = Signal()
    emergency_stop_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.resource_combo = QComboBox()
        self.resource_combo.setEditable(True)
        self.resource_combo.setMinimumWidth(360)

        self.refresh_button = QPushButton("Refresh")
        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        self.emergency_button = QPushButton("Emergency Stop")
        self.emergency_button.setObjectName("emergencyButton")

        self.identity_label = QLabel("IDN: -")
        self.identity_label.setWordWrap(True)
        self.status_label = QLabel("Disconnected")
        self.status_label.setWordWrap(True)

        resource_row = QHBoxLayout()
        resource_row.addWidget(self.resource_combo, 1)
        resource_row.addWidget(self.refresh_button)

        buttons = QHBoxLayout()
        buttons.addWidget(self.connect_button)
        buttons.addWidget(self.disconnect_button)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("VISA Resource", resource_row)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.emergency_button)
        layout.addWidget(self.identity_label)
        layout.addWidget(self.status_label)

        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self.connect_button.clicked.connect(self._emit_connect)
        self.disconnect_button.clicked.connect(self.disconnect_requested.emit)
        self.emergency_button.clicked.connect(self.emergency_stop_requested.emit)
        self.set_connected(False)

    def set_resources(self, resources: list[str], preferred: str | None = None) -> None:
        current = preferred or self.resource_combo.currentText().strip()
        self.resource_combo.clear()
        self.resource_combo.addItems(resources)
        if current:
            index = self.resource_combo.findText(current)
            if index >= 0:
                self.resource_combo.setCurrentIndex(index)
            else:
                self.resource_combo.setEditText(current)

    def set_identity(self, identity: str) -> None:
        self.identity_label.setText(f"IDN: {identity or '-'}")

    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def set_connected(self, connected: bool) -> None:
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.resource_combo.setEnabled(not connected)
        self.refresh_button.setEnabled(not connected)

    def _emit_connect(self) -> None:
        resource = self.resource_combo.currentText().strip()
        self.connect_requested.emit(resource)
