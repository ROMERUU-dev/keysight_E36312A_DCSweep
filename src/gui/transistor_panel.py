from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class TransistorPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        for text in (
            "MOSFET Output Curves: ID vs VDS for multiple VGS values.",
            "MOSFET Transfer Curve: ID vs VGS, gm, Vth, sqrt(ID).",
            "BJT Curve Tracer: IC vs VCE using an external base resistor.",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            layout.addWidget(label)

        self.output_button = QPushButton("MOSFET Output Curves - Stage 2")
        self.transfer_button = QPushButton("MOSFET Transfer Curve - Stage 2")
        self.bjt_button = QPushButton("BJT Curve Tracer - Stage 2")
        for button in (self.output_button, self.transfer_button, self.bjt_button):
            button.setEnabled(False)
            layout.addWidget(button)
        layout.addStretch(1)
