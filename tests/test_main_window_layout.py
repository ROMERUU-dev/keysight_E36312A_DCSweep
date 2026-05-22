from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QScrollArea

from src.gui.main_window import MainWindow


def test_final_app_layout_hides_mock_controls_and_wraps_tabs(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(config_path=tmp_path / "config.json")
    window.resize(1920, 1080)
    window.show()
    app.processEvents()

    assert not hasattr(window.connection_panel, "mock_checkbox")
    assert not hasattr(window.ltspice_panel, "mock_model_combo")
    assert window.connection_panel.resource_combo.findText("MOCK::E36312A::INSTR") == -1
    assert all(isinstance(window.tabs.widget(index), QScrollArea) for index in range(window.tabs.count()))
    assert window.tabs.tabText(3) == "Advanced DC Sweep"

    ltspice_tab_index = 3
    window.tabs.setCurrentIndex(ltspice_tab_index)
    app.processEvents()
    ltspice_scroll = window.tabs.widget(ltspice_tab_index)
    assert isinstance(ltspice_scroll, QScrollArea)
    assert ltspice_scroll.horizontalScrollBar().maximum() == 0

    window.toggle_full_screen()
    app.processEvents()
    assert window.isFullScreen()

    window.toggle_full_screen()
    app.processEvents()
    assert not window.isFullScreen()
    assert not window.isMaximized()

    window.resize(820, 560)
    app.processEvents()
    assert window.width() == 820
    assert window.height() == 560

    window.close()
    app.processEvents()
